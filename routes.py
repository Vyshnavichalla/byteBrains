from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from functools import wraps
from models import User, db, Class, Assignment, Quiz, QuizQuestion, QuestionOption, QuizAttempt, AssignmentSubmission, QuizAnswer
from datetime import datetime

# Blueprints
main = Blueprint('main', __name__)
auth = Blueprint('auth', __name__)
teacher = Blueprint('teacher', __name__, url_prefix='/teacher')
student = Blueprint('student', __name__, url_prefix='/student')

# Decorators
def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_teacher():
            return "Access denied", 403
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_student():
            return "Access denied", 403
        return f(*args, **kwargs)
    return decorated_function

def redirect_authenticated_user():
    if current_user.is_authenticated:
        if current_user.is_teacher():
            return redirect(url_for('teacher.dashboard'))
        return redirect(url_for('student.dashboard'))
    return None

# Main routes
@main.route('/')
def index():
    return render_template('index.html')

# Auth routes
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
        
        user = User(username=username, email=email, role=role)
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

# Teacher routes
@teacher.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    classes = current_user.created_classes
    return render_template('teacher/dashboard.html', classes=classes)

@teacher.route('/create-class', methods=['GET', 'POST'])
@login_required
@teacher_required
def create_class():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        if not name:
            flash('Class name is required')
            return redirect(url_for('teacher.create_class'))
        
        new_class = Class(
            name=name,
            description=description,
            join_code=Class.generate_join_code(),
            teacher_id=current_user.id
        )
        
        db.session.add(new_class)
        db.session.commit()
        
        flash(f'Class created successfully! Join code: {new_class.join_code}')
        return redirect(url_for('teacher.dashboard'))
    
    return render_template('teacher/create_class.html')

@teacher.route('/class/<int:class_id>')
@login_required
@teacher_required
def class_details(class_id):
    class_obj = Class.query.get_or_404(class_id)
    if class_obj.teacher_id != current_user.id:
        abort(403)
    return render_template('teacher/class_details.html', class_obj=class_obj)

@teacher.route('/class/<int:class_id>/create-assignment', methods=['GET', 'POST'])
@login_required
@teacher_required
def create_assignment(class_id):
    class_obj = Class.query.get_or_404(class_id)
    if class_obj.teacher_id != current_user.id:
        abort(403)
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%dT%H:%M')
        max_points = int(request.form.get('max_points', 100))
        
        if not all([title, description, due_date]):
            flash('Please fill in all required fields')
            return redirect(url_for('teacher.create_assignment', class_id=class_id))
        
        assignment = Assignment(
            title=title,
            description=description,
            due_date=due_date,
            max_points=max_points,
            class_id=class_id
        )
        
        db.session.add(assignment)
        db.session.commit()
        
        flash('Assignment created successfully!')
        return redirect(url_for('teacher.class_details', class_id=class_id))
    
    return render_template('teacher/create_assignment.html', class_obj=class_obj)

@teacher.route('/class/<int:class_id>/create-quiz', methods=['GET', 'POST'])
@login_required
@teacher_required
def create_quiz(class_id):
    class_obj = Class.query.get_or_404(class_id)
    if class_obj.teacher_id != current_user.id:
        abort(403)
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%dT%H:%M')
        time_limit = request.form.get('time_limit')
        time_limit = int(time_limit) if time_limit else None
        
        if not all([title, due_date]):
            flash('Please fill in all required fields')
            return redirect(url_for('teacher.create_quiz', class_id=class_id))
        
        quiz = Quiz(
            title=title,
            description=description,
            due_date=due_date,
            time_limit=time_limit,
            class_id=class_id
        )
        
        db.session.add(quiz)
        db.session.commit()
        
        flash('Quiz created successfully! Add questions to your quiz.')
        return redirect(url_for('teacher.add_quiz_questions', class_id=class_id, quiz_id=quiz.id))
    
    return render_template('teacher/create_quiz.html', class_obj=class_obj)

@teacher.route('/class/<int:class_id>/quiz/<int:quiz_id>/questions', methods=['GET', 'POST'])
@login_required
@teacher_required
def add_quiz_questions(class_id, quiz_id):
    class_obj = Class.query.get_or_404(class_id)
    quiz = Quiz.query.get_or_404(quiz_id)
    
    if class_obj.teacher_id != current_user.id:
        abort(403)
    
    if request.method == 'POST':
        question_text = request.form.get('question_text')
        question_type = request.form.get('question_type')
        correct_answer = request.form.get('correct_answer')
        points = int(request.form.get('points', 1))
        
        if not all([question_text, question_type, correct_answer]):
            flash('Please fill in all required fields')
            return redirect(url_for('teacher.add_quiz_questions', class_id=class_id, quiz_id=quiz_id))
        
        question = QuizQuestion(
            quiz_id=quiz_id,
            question_text=question_text,
            question_type=question_type,
            correct_answer=correct_answer,
            points=points
        )
        
        db.session.add(question)
        
        # Add options for multiple choice questions
        if question_type == 'multiple_choice':
            options = request.form.getlist('options[]')
            for option_text in options:
                if option_text.strip():
                    option = QuestionOption(option_text=option_text)
                    question.options.append(option)
        
        db.session.commit()
        flash('Question added successfully!')
        
        if 'add_another' in request.form:
            return redirect(url_for('teacher.add_quiz_questions', class_id=class_id, quiz_id=quiz_id))
        return redirect(url_for('teacher.class_details', class_id=class_id))
    
    return render_template('teacher/add_quiz_questions.html', class_obj=class_obj, quiz=quiz)

# Teacher grading routes
@teacher.route('/assignment/<int:assignment_id>/submissions')
@login_required
@teacher_required
def view_submissions(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.class_obj.teacher_id != current_user.id:
        abort(403)
    
    submissions = AssignmentSubmission.query.filter_by(assignment_id=assignment_id).all()
    return render_template('teacher/view_submissions.html',
        assignment=assignment,
        submissions=submissions
    )

@teacher.route('/assignment/<int:assignment_id>/submission/<int:submission_id>/grade', methods=['POST'])
@login_required
@teacher_required
def grade_submission(assignment_id, submission_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    submission = AssignmentSubmission.query.get_or_404(submission_id)
    
    if assignment.class_obj.teacher_id != current_user.id:
        abort(403)
    
    grade = request.form.get('grade', type=int)
    feedback = request.form.get('feedback')
    
    if grade is not None and 0 <= grade <= assignment.max_points:
        submission.grade = grade
        submission.feedback = feedback
        db.session.commit()
        flash('Grade updated successfully!')
    else:
        flash('Invalid grade value!')
    
    return redirect(url_for('teacher.view_submissions', assignment_id=assignment_id))

@teacher.route('/quiz/<int:quiz_id>/attempts')
@login_required
@teacher_required
def view_quiz_attempts(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.class_obj.teacher_id != current_user.id:
        abort(403)
    
    attempts = QuizAttempt.query.filter_by(quiz_id=quiz_id).all()
    return render_template('teacher/view_quiz_attempts.html',
        quiz=quiz,
        attempts=attempts
    )

@teacher.route('/quiz/<int:quiz_id>/attempt/<int:attempt_id>/answer/<int:answer_id>/grade', methods=['POST'])
@login_required
@teacher_required
def grade_answer(quiz_id, attempt_id, answer_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    answer = QuizAnswer.query.get_or_404(answer_id)
    
    if quiz.class_obj.teacher_id != current_user.id:
        abort(403)
    
    points = request.form.get('points', type=int)
    question = QuizQuestion.query.get(answer.question_id)
    
    if points is not None and 0 <= points <= question.points:
        answer.points_earned = points
        attempt.calculate_score()
        db.session.commit()
        flash('Points updated successfully!')
    else:
        flash('Invalid points value!')
    
    return redirect(url_for('teacher.view_quiz_attempts', quiz_id=quiz_id))

# Student routes
@student.route('/class/<int:class_id>')
@login_required
@student_required
def class_view(class_id):
    class_obj = Class.query.get_or_404(class_id)
    if class_obj not in current_user.enrolled_classes:
        abort(403)
    return render_template('student/class_view.html', 
        class_obj=class_obj,
        now=datetime.utcnow(),
        datetime=datetime
    )

@student.route('/assignment/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
@student_required
def view_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.class_obj not in current_user.enrolled_classes:
        abort(403)
    
    submission = assignment.get_submission(current_user)
    
    if request.method == 'POST':
        if datetime.utcnow() > assignment.due_date:
            flash('Assignment is past due!')
            return redirect(url_for('student.view_assignment', assignment_id=assignment_id))
        
        submission_text = request.form.get('submission_text')
        if submission:
            submission.submission_text = submission_text
            submission.submitted_at = datetime.utcnow()
        else:
            submission = AssignmentSubmission(
                student_id=current_user.id,
                assignment_id=assignment_id,
                submission_text=submission_text
            )
            db.session.add(submission)
        
        db.session.commit()
        flash('Assignment submitted successfully!')
        return redirect(url_for('student.view_assignment', assignment_id=assignment_id))
    
    return render_template('student/view_assignment.html',
        assignment=assignment,
        submission=submission,
        now=datetime.utcnow(),
        datetime=datetime
    )

@student.route('/quiz/<int:quiz_id>')
@login_required
@student_required
def view_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.class_obj not in current_user.enrolled_classes:
        abort(403)
    
    attempts = QuizAttempt.query.filter_by(
        student_id=current_user.id,
        quiz_id=quiz_id
    ).order_by(QuizAttempt.started_at.desc()).all()
    
    return render_template('student/view_quiz.html',
        quiz=quiz,
        attempts=attempts,
        now=datetime.utcnow(),
        datetime=datetime
    )

@student.route('/quiz/<int:quiz_id>/start')
@login_required
@student_required
def start_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.class_obj not in current_user.enrolled_classes:
        abort(403)
    
    if datetime.utcnow() > quiz.due_date:
        flash('Quiz is past due!')
        return redirect(url_for('student.view_quiz', quiz_id=quiz_id))
    
    attempt = QuizAttempt(
        student_id=current_user.id,
        quiz_id=quiz_id,
        started_at=datetime.utcnow()
    )
    db.session.add(attempt)
    db.session.commit()
    
    return redirect(url_for('student.take_quiz', quiz_id=quiz_id, attempt_id=attempt.id))

@student.route('/quiz/<int:quiz_id>/attempt/<int:attempt_id>', methods=['GET', 'POST'])
@login_required
@student_required
def take_quiz(quiz_id, attempt_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    
    if quiz.class_obj not in current_user.enrolled_classes or attempt.student_id != current_user.id:
        abort(403)
    
    if attempt.completed_at:
        return redirect(url_for('student.review_quiz_attempt', quiz_id=quiz_id, attempt_id=attempt_id))
    
    if request.method == 'POST':
        for question in quiz.questions:
            answer_text = request.form.get(f'question_{question.id}')
            if answer_text:
                answer = QuizAnswer(
                    attempt_id=attempt_id,
                    question_id=question.id,
                    answer_text=answer_text,
                    is_correct=answer_text == question.correct_answer if question.question_type != 'short_answer' else None,
                    points_earned=question.points if answer_text == question.correct_answer and question.question_type != 'short_answer' else None
                )
                db.session.add(answer)
        
        attempt.completed_at = datetime.utcnow()
        if all(q.question_type != 'short_answer' for q in quiz.questions):
            attempt.calculate_score()
        db.session.commit()
        
        return redirect(url_for('student.review_quiz_attempt', quiz_id=quiz_id, attempt_id=attempt_id))
    
    return render_template('student/take_quiz.html',
        quiz=quiz,
        attempt=attempt,
        now=datetime.utcnow()
    )

@student.route('/quiz/<int:quiz_id>/attempt/<int:attempt_id>/review')
@login_required
@student_required
def review_quiz_attempt(quiz_id, attempt_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    
    if quiz.class_obj not in current_user.enrolled_classes or attempt.student_id != current_user.id:
        abort(403)
    
    if not attempt.completed_at:
        return redirect(url_for('student.take_quiz', quiz_id=quiz_id, attempt_id=attempt_id))
    
    return render_template('student/review_quiz.html',
        quiz=quiz,
        attempt=attempt
    )

@student.route('/dashboard')
@login_required
@student_required
def dashboard():
    classes = current_user.enrolled_classes
    return render_template('student/dashboard.html', 
        classes=classes,
        now=datetime.utcnow(),
        datetime=datetime
    )

@student.route('/join-class', methods=['GET', 'POST'])
@login_required
@student_required
def join_class():
    if request.method == 'POST':
        join_code = request.form.get('join_code')
        
        if not join_code:
            flash('Please enter a join code')
            return redirect(url_for('student.join_class'))
        
        class_to_join = Class.query.filter_by(join_code=join_code).first()
        
        if not class_to_join:
            flash('Invalid join code')
            return redirect(url_for('student.join_class'))
        
        if class_to_join in current_user.enrolled_classes:
            flash('You are already enrolled in this class')
            return redirect(url_for('student.dashboard'))
        
        current_user.enrolled_classes.append(class_to_join)
        db.session.commit()
        
        flash(f'Successfully joined {class_to_join.name}!')
        return redirect(url_for('student.dashboard'))
    
    return render_template('student/join_class.html') 