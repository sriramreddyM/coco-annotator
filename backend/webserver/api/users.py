from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_restplus import Namespace, Resource, reqparse
from uuid import uuid4

from database import UserModel
from config import Config
from ..util.query_util import fix_ids

from datetime import datetime, timedelta
import jwt
from flask import jsonify

import logging
logger = logging.getLogger('gunicorn.error')

api = Namespace('user', description='User related operations')

register = reqparse.RequestParser()
register.add_argument('username', required=True, location='json')
register.add_argument('password', required=True, location='json')
register.add_argument('email', location='json')
register.add_argument('name', location='json')

login = reqparse.RequestParser()
login.add_argument('password', required=True, location='json')
login.add_argument('username', required=True, location='json')

set_password = reqparse.RequestParser()
set_password.add_argument('password', required=True, location='json')
set_password.add_argument('new_password', required=True, location='json')


@api.route('/')
class User(Resource):
    @login_required
    def get(self):
        """ Get information of current user """
        if Config.LOGIN_DISABLED:
            return current_user.to_json()

        user_json = fix_ids(current_user)
        del user_json['password']

        return {'user': user_json}


@api.route('/password')
class UserPassword(Resource):

    @login_required
    @api.expect(register)
    def post(self):
        """ Set password of current user """
        args = set_password.parse_args()

        if check_password_hash(current_user.password, args.get('password')):
            current_user.update(password=generate_password_hash(args.get('new_password'), method='sha256'), new=False)
            return {'success': True}

        return {'success': False, 'message': 'Password does not match current passowrd'}, 400


@api.route('/register')
class UserRegister(Resource):
    @api.expect(register)
    def post(self):
        """ Creates user """

        users = UserModel.objects.count()

        if not Config.ALLOW_REGISTRATION and users != 0:
            return {'success': False, 'message': 'Registration of new accounts is disabled.'}, 400

        args = register.parse_args()
        username = args.get('username')

        if UserModel.objects(username__iexact=username).first():
            return {'success': False, 'message': 'Username already exists.'}, 400

        user = UserModel()
        user.username = args.get('username')
        user.password = generate_password_hash(args.get('password'), method='sha256')
        # user.api_key = uuid4()
        user.name = args.get('name')
        user.email = args.get('email')
        if users == 0:
            user.is_admin = True
        user.save()
        user._update_last_seen()

        login_user(user)

        user_json = fix_ids(current_user)
        del user_json['password']

        return {'success': True, 'user': user_json}


@api.route('/login')
class UserLogin(Resource):
    @api.expect(login)
    def post(self):
        """ Logs user in """
        args = login.parse_args()
        username = args.get('username')

        user = UserModel.objects(username__iexact=username).first()
        if user is None:
            return {'success': False, 'message': 'Could not authenticate user'}, 400

        if check_password_hash(user.password, args.get('password')):
            login_user(user)
            user._update_last_seen()
            # user_api_key = user.api_key
            # if user_api_key == '':
            #     user_api_key = uuid4()
            #     user.update(api_key=user_api_key)
            user_json = fix_ids(current_user)
            del user_json['password']
            
            logger.info(f'User {current_user.username} has LOGIN')

            return {'success': True, 'user': user_json}

        return {'success': False, 'message': 'Could not authenticate user'}, 400

@api.route('/login/token')
class UserTokenLogin(Resource):
    @api.expect(login)
    def post(self):
        """ Logs user in """
        args = login.parse_args()
        username = args.get('username')

        user = UserModel.objects(username__iexact=username).first()
        if user is None:
            return {'success': False, 'message': 'Could not authenticate user'}, 400

        if check_password_hash(user.password, args.get('password')):
            login_user(user)
            user._update_last_seen()
            # user_api_key = user.api_key
            # if user_api_key == '':
            #     user_api_key = uuid4()
            #     user.update(api_key=user_api_key)
            user_json = fix_ids(current_user)
            del user_json['password']
            
            logger.info(f'User {current_user.username} has LOGIN')

            token = jwt.encode({
                'sub': user.username,
                'iat':datetime.utcnow(),
                'exp': datetime.utcnow() + timedelta(minutes=300)},
                Config.SECRET_KEY)

            return jsonify({ 'token': token.decode('UTF-8') })

        return {'success': False, 'message': 'Could not authenticate user'}, 400

@api.route('/logout')
class UserLogout(Resource):
    @login_required
    def get(self):
        """ Logs user out """
        logger.info(f'User {current_user.username} has LOGOUT')
        logout_user()
        return {'success': True}

@api.route('/live')
class UserLive(Resource):
    @login_required
    def get(self):
        user = UserModel.objects(username__iexact=current_user.username).first()
        user.update(last_seen=datetime.utcnow())
        user_model = UserModel.objects
        present_time = datetime.utcnow()
        live_count = 0
        for user in user_model:
            user_last_seen = user.last_seen
            if user_last_seen is not None:
                if present_time > user_last_seen:
                    td = present_time - user_last_seen
                else:
                    td = user_last_seen - present_time
                td_mins = int(round(td.total_seconds() / 60))
                if td_mins <= 3:
                    live_count += 1
        return {'success': True, 'live_count': live_count}

@api.route('/leaderboard')
class Leaderboard(Resource):
    # @login_required
    def get(self):
        all_users = UserModel.objects()
        # apply filters
        participants = 0
        total_images = 0
        total_annotations = 0
        image_leaderboard = {}
        annotation_leaderboard = {}
        for user in all_users:
            if user.cs_images:
                image_leaderboard['user.username'] = user.cs_images
                total_images += user.cs_images
            if user.cs_annotations:
                annotation_leaderboard['user.username'] = user.cs_annotations
                total_annotations += user.cs_annotations

        
        leaderboard = {}
        leaderboard['images'] = total_images
        leaderboard['annotations'] = total_annotations


        return {'success': True, 'leaderboard': leaderboard, 'image_chart': image_leaderboard, 'annotation_chart': annotation_leaderboard} 