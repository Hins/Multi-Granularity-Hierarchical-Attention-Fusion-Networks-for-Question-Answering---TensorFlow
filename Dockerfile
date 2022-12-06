# syntax=docker/dockerfile:1
 
FROM python:3.7.8

ADD . /code

WORKDIR /code

COPY requirements.txt requirements.txt
RUN pip install -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r requirements.txt  || true
 
COPY . .
 
CMD python /code/code/monitoring.py --mon yes --input /input --result /result
