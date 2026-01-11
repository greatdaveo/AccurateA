#
python3 -m venv .venv
# Virtual env
source .venv/bin/activate
# Run
uvicorn main:app --reload

docker build -t accuratea-test . 
docker run -p 8000:8000 --env-file .env accuratea-test