FROM python:3.12

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR app/

COPY  requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD [ "uvicorn" , "main:app" , "--host" ,"0.0.0.0" ]
