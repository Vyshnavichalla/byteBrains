from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from functools import wraps
from models import db, Class, Assignment, Quiz, Submission, QuizAttempt, QuizAnswer
from datetime import datetime

student = Blueprint('student', __name__, url_prefix='/student')

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_student():
            return "Access denied", 403
        return f(*args, **kwargs)
    return decorated_function

@student.route('/dashboard')
@login_required
@student_required
def dashboard():
    now = datetime.utcnow()
    return render_template('student/dashboard.html', 
                         classes=current_user.enrolled_classes,
                         now=now,
                         datetime=datetime)

@student.route('/class/<int:class_id>')
@login_required
@student_required
def class_view(class_id):
    class_obj = Class.query.get_or_404(class_id)
    
    # Check if student is enrolled in this class
    if class_obj not in current_user.enrolled_classes:
        abort(403)  # Forbidden
    
    return render_template('student/class_view.html',
                         class_obj=class_obj,
                         datetime=datetime)

@student.route('/quiz/<int:quiz_id>')
@login_required
@student_required
def view_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Check if student is enrolled in this class
    if quiz.class_obj not in current_user.enrolled_classes:
        abort(403)  # Forbidden
    
    # Get all attempts for this student
    attempts = QuizAttempt.query.filter_by(
        student_id=current_user.id,
        quiz_id=quiz_id
    ).order_by(QuizAttempt.started_at.desc()).all()
    
    return render_template('student/view_quiz.html',
                         quiz=quiz,
                         attempts=attempts,
                         datetime=datetime)

@student.route('/quiz/<int:quiz_id>/start')
@login_required
@student_required
def start_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Check if student is enrolled in this class
    if quiz.class_obj not in current_user.enrolled_classes:
        abort(403)  # Forbidden
    
    # Check if quiz is past due
    if datetime.utcnow() > quiz.due_date:
        flash('This quiz is past due')
        return redirect(url_for('student.view_quiz', quiz_id=quiz_id))
    
    # Create new attempt
    attempt = QuizAttempt(
        quiz_id=quiz_id,
        student_id=current_user.id
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
    
    # Check if student is enrolled and attempt belongs to them
    if quiz.class_obj not in current_user.enrolled_classes or attempt.student_id != current_user.id:
        abort(403)  # Forbidden
    
    # Check if attempt is already completed
    if attempt.completed_at:
        return redirect(url_for('student.review_quiz_attempt', quiz_id=quiz_id, attempt_id=attempt_id))
    
    # Check if quiz is past due
    if datetime.utcnow() > quiz.due_date:
        flash('This quiz is past due')
        return redirect(url_for('student.view_quiz', quiz_id=quiz_id))
    
    if request.method == 'POST':
        total_points = 0
        
        for question in quiz.questions:
            answer_text = request.form.get(f'question_{question.id}')
            
            if not answer_text:
                flash('All questions must be answered')
                return redirect(url_for('student.take_quiz', quiz_id=quiz_id, attempt_id=attempt_id))
            
            # Check if answer is correct
            is_correct = answer_text.lower() == question.correct_answer.lower()
            points_earned = question.points if is_correct else 0
            total_points += points_earned
            
            # Save answer
            answer = QuizAnswer(
                attempt_id=attempt_id,
                question_id=question.id,
                student_answer=answer_text,
                is_correct=is_correct,
                points_earned=points_earned
            )
            db.session.add(answer)
        
        # Complete attempt
        attempt.completed_at = datetime.utcnow()
        attempt.score = total_points
        db.session.commit()
        
        return redirect(url_for('student.review_quiz_attempt', quiz_id=quiz_id, attempt_id=attempt_id))
    
    return render_template('student/take_quiz.html',
                         quiz=quiz,
                         attempt=attempt,
                         datetime=datetime)

@student.route('/quiz/<int:quiz_id>/attempt/<int:attempt_id>/review')
@login_required
@student_required
def review_quiz_attempt(quiz_id, attempt_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    
    # Check if student is enrolled and attempt belongs to them
    if quiz.class_obj not in current_user.enrolled_classes or attempt.student_id != current_user.id:
        abort(403)  # Forbidden
    
    # Check if attempt is completed
    if not attempt.completed_at:
        return redirect(url_for('student.take_quiz', quiz_id=quiz_id, attempt_id=attempt_id))
    
    return render_template('student/review_quiz_attempt.html',
                         quiz=quiz,
                         attempt=attempt,
                         datetime=datetime)

@student.route('/assignment/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
@student_required
def view_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    
    # Check if student is enrolled in this class
    if assignment.class_obj not in current_user.enrolled_classes:
        abort(403)  # Forbidden
    
    # Get existing submission if any
    submission = Submission.query.filter_by(
        student_id=current_user.id,
        assignment_id=assignment_id
    ).first()
    
    if request.method == 'POST':
        # Check if assignment is past due
        if datetime.utcnow() > assignment.due_date:
            flash('Cannot submit after due date')
            return redirect(url_for('student.view_assignment', assignment_id=assignment_id))
        
        submission_text = request.form.get('submission_text')
        
        if not submission_text:
            flash('Submission text is required')
            return redirect(url_for('student.view_assignment', assignment_id=assignment_id))
        
        if submission:
            # Update existing submission
            submission.submission_text = submission_text
            submission.submitted_at = datetime.utcnow()
            flash('Submission updated successfully!')
        else:
            # Create new submission
            submission = Submission(
                submission_text=submission_text,
                assignment_id=assignment_id,
                student_id=current_user.id
            )
            db.session.add(submission)
            flash('Assignment submitted successfully!')
        
        db.session.commit()
        return redirect(url_for('student.view_assignment', assignment_id=assignment_id))
    
    return render_template('student/view_assignment.html',
                         assignment=assignment,
                         submission=submission,
                         datetime=datetime)

@student.route('/join-class', methods=['GET', 'POST'])
@login_required
@student_required
def join_class():
    if request.method == 'POST':
        join_code = request.form.get('join_code')
        class_obj = Class.query.filter_by(join_code=join_code).first()
        
        if not class_obj:
            flash('Invalid join code')
            return redirect(url_for('student.join_class'))
        
        if class_obj in current_user.enrolled_classes:
            flash('You are already enrolled in this class')
            return redirect(url_for('student.dashboard'))
        
        current_user.enrolled_classes.append(class_obj)
        db.session.commit()
        
        flash(f'Successfully joined {class_obj.name}!')
        return redirect(url_for('student.dashboard'))
    
    return render_template('student/join_class.html') 