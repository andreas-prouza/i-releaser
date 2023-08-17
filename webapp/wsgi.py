from index import app

# http://192.168.0.2:8081/getlogs_api/220

if __name__ == '__main__':
    app.run(port=app.config["PORT"],host=app.config['HOST'])