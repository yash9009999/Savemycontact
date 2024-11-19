sudo apt-get update
sudo apt install python3-pip
sudo apt install python3-virtualenv
virtualenv venv
ls
virtualenv venv
ls
source venv/bin/activate
sudo apt install git
git clone https://github.com/yash9009999/git.git
ls
mv git/* .
ls
v
rmdir git
rm -rf git
ls
clear
python3 app.py
ls
pip install -r requirements.txt
python3 app.py
sudo apt-get install tesseract-ocr
tesseract -v
python3 app.py
ls
source venv/bin/activate
ls
pip install gunicorn
gunicorn app:app
gunicorn -b 0.0.0.0:5000 app:app
nohup gunicorn -w 5 -b 0.0.0.0:5000 app:app &
ls
nano nohup.out
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/bin/certbot
certbot --apache
nano nohup.out
gunicorn --timeout 120 -w 4 -b 0.0.0.0:5000 app:app
sudo lsof -i :5000
sudo kill -9 4436 4442 4466 4911 4955 4957
sudo lsof -i :5000
gunicorn --timeout 120 -w 4 -b 0.0.0.0:5000 app:app
nohup gunicorn --timeout 120 -w 4 -b 0.0.0.0:5000 app:app &
nano nohup.out
