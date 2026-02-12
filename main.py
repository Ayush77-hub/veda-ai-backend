from app import app

# This file is needed because the Replit workflow is configured to run main.py
# The actual application logic is in app.py

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
    
