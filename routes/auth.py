from flask import Blueprint, render_template, request, redirect, url_for, session, make_response
from datetime import datetime
from models import get_db_session, authenticate_user, create_user, UserSession

auth_bp = Blueprint('auth', __name__)

db = get_db_session()

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    current_year = datetime.now().year
    if 'user_id' in session:
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        email = request.form.get('email', '').strip() or None
        if not username or not password:
            error = "用户名和密码不能为空"
        elif len(username) < 3:
            error = "用户名长度不能少于3个字符"
        elif len(password) < 6:
            error = "密码长度不能少于6个字符"
        elif password != confirm_password:
            error = "两次输入的密码不一致"
        else:
            user, err = create_user(db, username, password, email)
            if user:
                session['user_id'] = user.id
                session['username'] = user.username
                session['is_admin'] = user.is_admin
                session_id = UserSession.create_session(
                    db, user.id, ip_address=request.remote_addr, user_agent=request.user_agent.string
                )
                user.last_login = datetime.now()
                db.commit()
                response = make_response(redirect(url_for('index')))
                response.set_cookie('session_id', session_id, max_age=30*24*60*60, httponly=True)
                return response
            else:
                error = err
    return render_template('register.html', error=error, current_year=current_year)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    current_year = datetime.now().year
    if 'user_id' in session:
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', '') == 'on'
        user = authenticate_user(db, username, password)
        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            if remember:
                session_id = UserSession.create_session(
                    db, user.id, ip_address=request.remote_addr, user_agent=request.user_agent.string
                )
                user.last_login = datetime.now()
                db.commit()
                response = make_response(redirect(url_for('index')))
                response.set_cookie('session_id', session_id, max_age=30*24*60*60, httponly=True)
                return response
            user.last_login = datetime.now()
            db.commit()
            return redirect(url_for('index'))
        else:
            error = "用户名或密码错误"
    return render_template('login.html', error=error, current_year=current_year)

@auth_bp.route('/logout')
def logout():
    session_id = request.cookies.get('session_id')
    if session_id:
        UserSession.delete_session(db, session_id)
    session.clear()
    response = make_response(redirect(url_for('auth.login')))
    response.delete_cookie('session_id')
    return response 