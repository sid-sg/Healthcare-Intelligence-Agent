# Steps
```sh
python3 -m venv venv
```
```sh
source venv/bin/activate
```
```sh
pip install -r requirements.txt
```
```sh
uvicorn main:app --reload --port 8000
```

# Test API
### Test API health
```sh
curl http://localhost:8000/health
```
### Test Chat API
```sh
curl -X 'POST' \
  'http://localhost:8000/chat' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "message": "Hello",
}'
```