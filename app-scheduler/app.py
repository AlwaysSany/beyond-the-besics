from flask_ap_scheduler_app import create_app


app = create_app()


if __name__ == "__main__":
    print("Running development server on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", debug=True)