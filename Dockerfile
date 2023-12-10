FROM python:3.11
WORKDIR /bot
COPY requirements.txt /bot/
COPY . /bot
RUN apt-get update && \
    apt-get -y install ffmpeg libavcodec-extra && \
    pip install --upgrade pip && \
    pip install -r requirements.txt 
CMD python main.py
