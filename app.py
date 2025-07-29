from flask import Flask
from application.database import db
app=None

def create_app():
    app=Flask(__name__)
    app.secret_key = 'H123H' 
    app.debug = True
    app.config["SQLALCHEMY_DATABASE_URI"]="sqlite:///parking.sqlite3"
    db.init_app(app)

    app.app_context().push()
    return app

app = create_app()
from application.controllers import *

if __name__=='__main__':
    #db.create_all()
    #user1= User(email="admin123@gmail.com", password_hash="1234", is_admin=True)
    #db.session.add(user1)
    #db.session.commit()
    app.run()