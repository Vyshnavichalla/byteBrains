from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import User, db

auth = Blueprint('auth', __name__)

def redirect_authenticated_user():
    if current_user.is_authenticated:
        if current_user.is_teacher():
            return redirect(url_for('teacher.dashboard'))
        return redirect(url_for('student.dashboard'))
    return None

@auth.route('/login', methods=['GET', 'POST'])
def login():
    redirect_response = redirect_authenticated_user()
    if redirect_response:
        return redirect_response
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            if user.is_teacher():
                return redirect(url_for('teacher.dashboard'))
            return redirect(url_for('student.dashboard'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    redirect_response = redirect_authenticated_user()
    if redirect_response:
        return redirect_response
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        name = request.form.get('name')
        password = request.form.get('password')
        role = request.form.get('role')
        
        if not role or role not in ['teacher', 'student']:
            flash('Please select a valid role')
            return redirect(url_for('auth.signup'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('auth.signup'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('auth.signup'))
        
        if not name:
            name = username
        
        user = User(username=username, email=email, role=role, name=name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.')
        return redirect(url_for('auth.login'))
    
    return render_template('signup.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index')) 