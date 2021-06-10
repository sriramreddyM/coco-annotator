FROM jsbroks/coco-annotator:python-env

WORKDIR /workspace/

COPY ./backend/ /workspace/
COPY ./.git /workspace/.git

RUN pip install -r requirements.txt

RUN python set_path.py

ENV FLASK_ENV=development
ENV DEBUG=true

EXPOSE 5000
CMD gunicorn -c webserver/gunicorn_config.py webserver:app --no-sendfile


