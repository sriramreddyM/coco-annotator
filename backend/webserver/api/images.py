from flask_restplus import Namespace, Resource, reqparse
from flask_login import login_required, current_user
from werkzeug.datastructures import FileStorage
from flask import send_file

from ..util import query_util, coco_util
from database import (
    UserModel,
    ImageModel,
    DatasetModel,
    AnnotationModel
)

from PIL import Image
import datetime
import os
import io

from geojson import Point

import logging
logger = logging.getLogger('gunicorn.error')

api = Namespace('image', description='Image related operations')


image_all = reqparse.RequestParser()
image_all.add_argument('fields', required=False, type=str)
image_all.add_argument('page', default=1, type=int)
image_all.add_argument('per_page', default=50, type=int, required=False)

image_upload = reqparse.RequestParser()
image_upload.add_argument('image', location='files',
                          type=FileStorage, required=True,
                          help='PNG or JPG file')
image_upload.add_argument('dataset_id', required=True, type=int,
                          help='Id of dataset to insert image into')
image_upload.add_argument('latitude', type=float, help='latitude of the image if exists', default=None)
image_upload.add_argument('longitude', type=float, help='longitude of the image if exists', default=None)

image_download = reqparse.RequestParser()
image_download.add_argument('asAttachment', type=bool, default=False)
image_download.add_argument('thumbnail', type=bool, default=False)
image_download.add_argument('width', type=int)
image_download.add_argument('height', type=int)

copy_annotations = reqparse.RequestParser()
copy_annotations.add_argument('category_ids', location='json', type=list,
                              required=False, default=None, help='Categories to copy')

image_updates = reqparse.RequestParser()
image_updates.add_argument('cs_annotating', location='json', type=bool, default=False)
image_updates.add_argument('is_annotations_added', location='json', type=bool, default=False) 

flag_args = reqparse.RequestParser()
flag_args.add_argument('image_id', location='json', type=int)
flag_args.add_argument('is_flagged', location='json', type=bool, default=False)

approve_args = reqparse.RequestParser()
approve_args.add_argument('image_id', location='json', type=int)

@api.route('/')
class Images(Resource):

    @api.expect(image_all)
    @login_required
    def get(self):
        """ Returns all images """
        args = image_all.parse_args()
        per_page = args['per_page']
        page = args['page']-1
        fields = args.get('fields', '')

        images = current_user.images.filter(deleted=False)
        total = images.count()
        pages = int(total/per_page) + 1

        images = images.skip(page*per_page).limit(per_page)
        if fields:
            images = images.only(*fields.split(','))

        return {
            "total": total,
            "pages": pages,
            "page": page,
            "fields": fields,
            "per_page": per_page,
            "images": query_util.fix_ids(images.all())
        }

    @api.expect(image_upload)
    # @login_required
    def post(self):
        """ Creates an image """
        args = image_upload.parse_args()
        image = args['image']

        dataset_id = args['dataset_id']
        latitude = args['latitude']
        longitude = args['longitude']
        try:
            dataset = DatasetModel.objects.get(id=dataset_id)
        except:
            return {'message': 'dataset does not exist'}, 400

        # check if current user exists or dataset is public
        if current_user or dataset['is_public']:
        
            directory = dataset.directory
            path = os.path.join(directory, image.filename)

            if os.path.exists(path):
                return {'message': 'file already exists'}, 400

            pil_image = Image.open(io.BytesIO(image.read()))

            pil_image.save(path)

            image.close()
            pil_image.close()
            if latitude is not None and longitude is not None:
                gps_point = Point((float(latitude), float(longitude)))
            else:
                gps_point = None
            db_image = ImageModel.create_from_path(path, dataset_id, current_user.username, gps_point).save()
            # to do @sriram
            # generate thubnail immediately after uploading
            return db_image.id
        else:
            return {'message': 'Upload not permitted'}, 400


@api.route('/<int:image_id>')
class ImageId(Resource):

    @api.expect(image_download)
    #@login_required
    def get(self, image_id):
        """ Returns category by ID """
        args = image_download.parse_args()
        as_attachment = args.get('asAttachment')
        thumbnail = args.get('thumbnail')

        image = current_user.images.filter(id=image_id, deleted=False).first()

        if image is None:
            return {'success': False}, 400

        width = args.get('width')
        height = args.get('height')
        
        if not width:
            width = image.width
        if not height:
            height = image.height
        
        pil_image = image.open_thumbnail() if thumbnail else Image.open(image.path)

        pil_image.thumbnail((width, height), Image.ANTIALIAS)
        image_io = io.BytesIO()
        pil_image = pil_image.convert("RGB")
        pil_image.save(image_io, "JPEG", quality=90)
        image_io.seek(0)

        return send_file(image_io, attachment_filename=image.file_name, as_attachment=as_attachment)

    # to do @sriram
    # uncomment below to delete from cs
    @login_required
    def delete(self, image_id):
        """ Deletes an image by ID """
        image = current_user.images.filter(id=image_id, deleted=False).first()
        if image is None:
            return {"message": "Invalid image id"}, 400

        if not current_user.can_delete(image):
            return {"message": "You do not have permission to download the image"}, 403

        image.update(set__deleted=True, set__deleted_date=datetime.datetime.now())
        return {"success": True}
    
    @api.expect(image_updates)
    def put(self, image_id):
        args = image_updates.parse_args()
        logger.info(f'args are, {args}')
        cs_annotating = args.get('cs_annotating')
        is_annotations_added = args.get('is_annotations_added')

        image = current_user.images.filter(id=image_id, deleted=False).first()
        if image is None:
            return {"message": "Invalid image id"}, 400
        
        if is_annotations_added:
            logger.info(f'current user: {current_user.username}')
            image.update(set__cs_annotating=cs_annotating, add_to_set__cs_annotated=current_user.username)
        else:
            logger.info(f'something wrong saving user')
            image.update(set__cs_annotating=cs_annotating)

        image_id = image.id
        image = current_user.images.filter(id=image_id, deleted=False).first()
        return{"message": "Updated image", "annotating": image.cs_annotating, "annotated by": image.cs_annotated}


@api.route('/copy/<int:from_id>/<int:to_id>/annotations')
class ImageCopyAnnotations(Resource):

    @api.expect(copy_annotations)
    @login_required
    def post(self, from_id, to_id):
        args = copy_annotations.parse_args()
        category_ids = args.get('category_ids')

        image_from = current_user.images.filter(id=from_id).first()
        image_to = current_user.images.filter(id=to_id).first()

        if image_from is None or image_to is None:
            return {'success': False, 'message': 'Invalid image ids'}, 400

        if image_from == image_to:
            return {'success': False, 'message': 'Cannot copy self'}, 400

        if image_from.width != image_to.width or image_from.height != image_to.height:
            return {'success': False, 'message': 'Image sizes do not match'}, 400

        if category_ids is None:
            category_ids = DatasetModel.objects(id=image_from.dataset_id).first().categories

        query = AnnotationModel.objects(
            image_id=image_from.id,
            category_id__in=category_ids,
            deleted=False
        )

        return {'annotations_created': image_to.copy_annotations(query)}


@api.route('/<int:image_id>/coco')
class ImageCoco(Resource):

    @login_required
    def get(self, image_id):
        """ Returns coco of image and annotations """
        image = current_user.images.filter(id=image_id).exclude('deleted_date').first()
        
        if image is None:
            return {"message": "Invalid image ID"}, 400

        if not current_user.can_download(image):
            return {"message": "You do not have permission to download the images's annotations"}, 403

        return coco_util.get_image_coco(image_id)

@api.route('/flag')
class ImageFlag(Resource):

    # @login_required
    @api.expect(flag_args)
    def post(self, image_id):
        
        args = flag_args.parse_args()
        image_id = args.get('image_id')
        is_flag = args.get('is_flagged')
        image = current_user.images.filter(id=image_id).first()
        if is_flag:
            image.update(add_to_set__cs_flagged_users=current_user.username)
        return {'success': True}

@api.route('/approve')
class ImageApprove(Resource):

    @login_required
    @api.expect(approve_args)
    def post(self, image_id):
        args = approve_args.parse_args()
        image_id = args.get('image_id')
        image = current_user.images.filter(id=image_id).first()
        image.update(set__approved_by=current_user.username)
        image_uploaded_by = image.uploaded_by
        uploaded_user = UserModel.objects(username__iexact=image_uploaded_by).first()
        cs_images = uploaded_user.cs_images + 1
        uploaded_user.update(set__cs_images= cs_images)
        return {'success': True}