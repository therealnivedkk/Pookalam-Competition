from flask import Flask, render_template, request, redirect, flash, url_for, jsonify
from bson import ObjectId
import os
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from functools import wraps

app = Flask(__name__)
app.secret_key = "pookalam_secret_key_2026"

# --- Configuration ---
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- MongoDB Connection ---
import os
client = MongoClient(os.environ.get("MONGO_URI"))
db = client["pookalam_db"]
teams_col = db["teams"]
users_col = db["users"]

# default admin login credintials
if not users_col.find_one({"role": "admin"}):
    users_col.insert_one({
        "username": "admin",
        "password": "admin@2026",
        "role": "admin"
    })

# --- Flask-Login Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

class User(UserMixin):
    def __init__(self, user_doc):
        self.id = str(user_doc["_id"])
        self.username = user_doc.get("username", "Guest")
        self.role = user_doc.get("role", "user")

@login_manager.user_loader
def load_user(user_id):
    try:
        doc = users_col.find_one({"_id": ObjectId(user_id)})
        return User(doc) if doc else None
    except:
        return None

# --- Access Decorators ---
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Admin access only.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def judge_required(f):
    @wraps(f)
    def decorated_fun(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "judge":
            flash("Judge access only.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_fun

# --- General Routes ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register')
def register():
    return render_template("register.html")

@app.route('/add_team', methods=['POST'])
def add_team():
    team_name = request.form.get('team_name')
    college   = request.form.get('college')
    members   = [m.strip() for m in request.form.get('members', '').split(',')]
    theme     = request.form.get('theme')

    if len(members) > 5:
        flash("Maximum 5 members allowed!", "error")
        return redirect(url_for('register'))

    image_filename = None
    if 'pookalam_image' in request.files:
        file = request.files['pookalam_image']
        if file and allowed_file(file.filename):
            image_filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

    team = {
        "team_name":      team_name,
        "college":        college,
        "members":        members,
        "theme":          theme,
        "pookalam_image": image_filename,
        "scores":         []
    }
    teams_col.insert_one(team)
    flash("Team registered successfully!", "success")
    return redirect(url_for('home'))

# --- Teams (Admin only) ---
@app.route('/teams')
@login_required
def view_teams():
    teams = list(teams_col.find())
    return render_template("teams.html", teams=teams)

# --- Leaderboard Routes ---
@app.route('/leaderboard')
def leaderboard():
    pipeline = [
        {"$unwind": {"path": "$scores", "preserveNullAndEmptyArrays": True}},
        {"$addFields": {
            "total_per_judge": {
                "$add": [
                    {"$ifNull": ["$scores.symmetry", 0]},
                    {"$ifNull": ["$scores.color", 0]},
                    {"$ifNull": ["$scores.variety", 0]}
                ]
            }
        }},
        {"$group": {
            "_id":         "$team_name",
            "college":     {"$first": "$college"},
            "total_score": {"$sum": "$total_per_judge"},
            "judge_count": {"$sum": {"$cond": [{"$gt": ["$total_per_judge", 0]}, 1, 0]}}
        }},
        {"$addFields": {
            "avg_score": {
                "$cond": [
                    {"$eq": ["$judge_count", 0]},
                    0,
                    {"$divide": ["$total_score", "$judge_count"]}
                ]
            }
        }},
        {"$sort": {"total_score": -1}},
        {"$setWindowFields": {
            "sortBy": {"total_score": -1},
            "output": {"rank": {"$rank": {}}}
        }}
    ]
    result = list(teams_col.aggregate(pipeline))
    return render_template("leaderboard.html", teams=result)

@app.route('/api/leaderboard')
def api_leaderboard():
    pipeline = [
        {"$unwind": {"path": "$scores", "preserveNullAndEmptyArrays": True}},
        {"$addFields": {
            "total_per_judge": {
                "$add": [
                    {"$ifNull": ["$scores.symmetry", 0]},
                    {"$ifNull": ["$scores.color", 0]},
                    {"$ifNull": ["$scores.variety", 0]}
                ]
            }
        }},
        {"$group": {
            "_id":         "$team_name",
            "college":     {"$first": "$college"},
            "total_score": {"$sum": "$total_per_judge"},
            "judge_count": {"$sum": {"$cond": [{"$gt": ["$total_per_judge", 0]}, 1, 0]}}
        }},
        {"$addFields": {
            "avg_score": {
                "$cond": [
                    {"$eq": ["$judge_count", 0]},
                    0,
                    {"$divide": ["$total_score", "$judge_count"]}
                ]
            }
        }},
        {"$sort": {"total_score": -1}},
        {"$setWindowFields": {
            "sortBy": {"total_score": -1},
            "output": {"rank": {"$rank": {}}}
        }}
    ]
    result = list(teams_col.aggregate(pipeline))
    return jsonify(result)

# --- Authentication ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_doc = users_col.find_one({"username": username, "password": password})
        if user_doc:
            user = User(user_doc)
            login_user(user)
            flash(f"Welcome {user.username}!", "success")
            return redirect(url_for("admin_dashboard" if user.role == "admin" else "judge_dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("home"))

# --- Admin Section ---
@app.route('/admin')
@admin_required
def admin_dashboard():
    judges = list(users_col.find({"role": "judge"}))
    return render_template("admin_dashboard.html", judges=judges)

@app.route('/edit_team/<team_id>')
@admin_required
def edit_team(team_id):
    team = teams_col.find_one({"_id": ObjectId(team_id)})
    if not team:
        flash("Team not found.", "danger")
        return redirect(url_for("view_teams"))
    return render_template("edit_team.html", team=team)

@app.route('/update_team/<team_id>', methods=['POST'])
@admin_required
def update_team(team_id):
    team_name = request.form.get('team_name')
    college   = request.form.get('college')
    members   = [m.strip() for m in request.form.get('members', '').split(',')]
    theme     = request.form.get('theme')

    teams_col.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {
            "team_name": team_name,
            "college":   college,
            "members":   members,
            "theme":     theme
        }}
    )
    flash("Team updated successfully!", "success")
    return redirect(url_for("view_teams"))

@app.route('/admin/create_judge', methods=['POST'])
@admin_required
def create_judge():
    username = request.form['username']
    password = request.form['password']
    if users_col.find_one({"username": username}):
        flash("Judge already exists.", "danger")
    else:
        users_col.insert_one({
            "username": username,
            "password": password,
            "role":     "judge"
        })
        flash("Judge created successfully!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route('/admin/delete_judge/<judge_id>', methods=['POST'])
@admin_required
def delete_judge(judge_id):
    users_col.delete_one({"_id": ObjectId(judge_id)})
    flash("Judge deleted.", "info")
    return redirect(url_for("admin_dashboard"))

@app.route('/admin/delete_team/<team_id>', methods=['POST'])
@admin_required
def delete_team(team_id):
    teams_col.delete_one({"_id": ObjectId(team_id)})
    flash("Team deleted.", "info")
    return redirect(url_for("view_teams"))

# --- Judge Section ---
@app.route('/judge')
@judge_required
def judge_dashboard():
    teams = list(teams_col.find())
    return render_template("judge_dashboard.html", teams=teams)

@app.route('/score_form/<team_id>')
@judge_required
def score_form(team_id):
    team = teams_col.find_one({"_id": ObjectId(team_id)})
    return render_template("score_form.html", team=team)

@app.route('/submit_score', methods=['POST'])
@judge_required
def submit_score():
    team_id = request.form.get('team_id')

    try:
        symmetry = float(request.form.get('symmetry', 0))
        color    = float(request.form.get('color', 0))
        variety  = float(request.form.get('variety', 0))
    except ValueError:
        flash("Invalid score format.", "danger")
        return redirect(url_for("judge_dashboard"))

    # clamp scores between 1 and 10
    symmetry = max(0.0, min(10.0, symmetry))
    color    = max(0.0, min(10.0, color))
    variety  = max(0.0, min(10.0, variety))

    new_score = {
        "judge":    current_user.username,
        "symmetry": symmetry,
        "color":    color,
        "variety":  variety
    }

    # allows judges to rescore a team
    teams_col.update_one(
        {"_id": ObjectId(team_id)},
        {"$pull": {"scores": {"judge": current_user.username}}}
    )
    teams_col.update_one(
        {"_id": ObjectId(team_id)},
        {"$push": {"scores": new_score}}
    )

    flash("Score submitted successfully!", "success")
    return redirect(url_for("judge_dashboard"))

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=1000)