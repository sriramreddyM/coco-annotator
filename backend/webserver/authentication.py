from flask_login import LoginManager, AnonymousUserMixin
from werkzeug.security import check_password_hash
from database import (
    UserModel,
    DatasetModel,
    CategoryModel,
    AnnotationModel,
    ImageModel
)
from config import Config
from uuid import uuid4
from flask import jsonify
import jwt

import logging
logger = logging.getLogger('gunicorn.error')

login_manager = LoginManager()


class AnonymousUser(AnonymousUserMixin):
    @property
    def datasets(self):
        return DatasetModel.objects

    @property
    def categories(self):
        return CategoryModel.objects

    @property
    def annotations(self):
        return AnnotationModel.objects

    @property
    def images(self):
        return ImageModel.objects

    @property
    def username(self):
        return "anonymous"

    @property
    def name(self):
        return "Anonymous User"

    @property
    def is_admin(self):
        return False

    def update(self, *args, **kwargs):
        pass

    def to_json(self):
        return {
            "admin": False,
            "username": self.username,
            "name": self.name,
            "is_admin": self.is_admin,
            "anonymous": True
        }

    def can_edit(self, model):
        return True

    def can_view(self, model):
        return True

    def can_download(self, model):
        return True

    def can_delete(self, model):
        return True


login_manager.anonymous_user = AnonymousUser


@login_manager.user_loader
def load_user(user_id):
    return UserModel.objects(id=user_id).first()


@login_manager.unauthorized_handler
def unauthorized():
    return {'success': False, 'message': 'Authorization required'}, 401


@login_manager.request_loader
def load_user_from_request(request):

    token = request.headers.get('Authorization')
    # logger.info(f'Trying login user from token, {token}')
    if token:
        decoded_token = jwt.decode(token, Config.SECRET_KEY)
        logger.info(f'Trying login user from token, {decoded_token["sub"]}')
        user = UserModel.query.filter_by(username=decoded_token['sub']).first()
        if user:
            return user
    return None



    # api_key = request.args.get('api_key')
    # if api_key and len(api_key) == 24:
    #     logger.info(f'Trying login with api key')
    #     user = UserModel.objects(id=api_key).first()
    #     if user:
    #         logger.info(f'{user.username} logged in with api key')
    #         return user

    # auth = request.authorization
    # if not auth:
    #     return None
    # user = UserModel.objects(username__iexact=auth.username).first()
    
    # # if not user.api_key:
    # #     logger.info(f'api key generating')
    # #     new_api_key = uuid4()
    # #     user.update(api_key=new_api_key)
    # #     user = UserModel.objects(username__iexact=auth.username).first()

    # if user and check_password_hash(user.password, auth.password):
    #     # login_user(user)
    #     return user
    # return None