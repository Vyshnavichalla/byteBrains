from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, jsonify
from flask_login import login_required, current_user
from functools import wraps
from models import db, Class, User, Assignment, Submission, Quiz, QuizAttempt, QuizAnswer, Question, QuestionOption
from datetime import datetime
import os
from services.ai_grading import grade_assignment, grade_quiz_answer, analyze_student_performance

teacher = Blueprint('teacher', __name__, url_prefix='/teacher')

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_teacher():
            return "Access denied", 403
        return f(*args, **kwargs)
    return decorated_function

@teacher.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    classes = current_user.classes_teaching
    return render_template('teacher/dashboard.html', classes=classes)

@teacher.route('/class/<int:class_id>')
@login_required
@teacher_required
def class_details(class_id):
    class_obj = Class.query.get_or_404(class_id)
    
    # Check if the current user is the teacher of this class
    if class_obj.teacher_id != current_user.id:
        abort(403)  # Forbidden
    
    return render_template('teacher/class_details.html',
                         class_obj=class_obj,
                         datetime=datetime)

@teacher.route('/submission/<int:submission_id>', methods=['GET', 'POST'])
@login_required
@teacher_required
def view_submission(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    assignment = submission.assignment
    
    # Check if teacher owns the class
    if assignment.class_obj.teacher_id != current_user.id:
        abort(403)
    
    if request.method == 'POST':
        # Check if auto-grade button was clicked
        if 'auto_grade' in request.form:
            # Use AI to grade the submission
            grading_result = grade_assignment(
                submission.submission_text,
                assignment.description,
                assignment.max_points
            )
            
            # Update submission with AI-generated grade and feedback
            submission.grade = grading_result["grade"]
            submission.feedback = grading_result["feedback"]
            
            # Store weak topics for later analysis
            if grading_result["weak_topics"]:
                submission.weak_topics = ", ".join(grading_result["weak_topics"])
            
            db.session.commit()
            flash('Submission auto-graded successfully!')
            return redirect(url_for('teacher.view_submission', submission_id=submission_id))
        else:
            # Manual grading
            grade = request.form.get('grade')
            feedback = request.form.get('feedback')
            
            if grade:
                try:
                    grade_float = float(grade)
                    if grade_float <= assignment.max_points:
                        submission.grade = grade_float
                        submission.feedback = feedback
                        db.session.commit()
                        flash('Grade saved successfully!')
                    else:
                        flash(f'Grade cannot exceed maximum points ({assignment.max_points})')
                except ValueError:
                    flash('Invalid grade value')
            
            return redirect(url_for('teacher.view_submission', submission_id=submission_id))
    
    return render_template('teacher/view_submission.html',
                         submission=submission,
                         assignment=assignment,
                         student=submission.student)

@teacher.route('/quiz/<int:quiz_id>/attempts')
@login_required
@teacher_required
def view_quiz_attempts(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Check if teacher owns the class
    if quiz.class_obj.teacher_id != current_user.id:
        abort(403)
    
    # Get all attempts for this quiz, grouped by student
    attempts_by_student = {}
    
    for attempt in quiz.attempts:
        student = User.query.get(attempt.student_id)
        if student not in attempts_by_student:
            attempts_by_student[student] = []
        attempts_by_student[student].append(attempt)
    
    # Sort attempts for each student by date (newest first)
    for student in attempts_by_student:
        attempts_by_student[student].sort(key=lambda a: a.started_at, reverse=True)
    
    return render_template('teacher/view_quiz_attempts.html',
                         quiz=quiz,
                         attempts_by_student=attempts_by_student)

@teacher.route('/quiz-attempt/<int:attempt_id>', methods=['GET', 'POST'])
@login_required
@teacher_required
def view_quiz_attempt_details(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    quiz = attempt.quiz
    
    # Check if teacher owns the class
    if quiz.class_obj.teacher_id != current_user.id:
        abort(403)
    
    if request.method == 'POST':
        if 'auto_grade' in request.form:
            # Use AI to grade all answers
            total_score = 0
            
            for question in quiz.questions:
                answer = QuizAnswer.query.filter_by(
                    attempt_id=attempt.id,
                    question_id=question.id
                ).first()
                
                if answer:
                    # Grade this answer using AI
                    result = grade_quiz_answer(
                        answer.student_answer,
                        question.correct_answer,
                        question.question_text,
                        question.points
                    )
                    
                    # Update answer with AI-generated results
                    answer.is_correct = result["is_correct"]
                    answer.points_earned = result["points_earned"]
                    answer.feedback = result["feedback"]
                    
                    total_score += result["points_earned"]
            
            # Update the attempt with the total score
            attempt.score = total_score
            db.session.commit()
            
            flash('Quiz attempt auto-graded successfully!')
            return redirect(url_for('teacher.view_quiz_attempt_details', attempt_id=attempt_id))
    
    # Get all answers for this attempt
    answers = QuizAnswer.query.filter_by(attempt_id=attempt.id).all()
    
    # Create a dictionary mapping question IDs to answers for easier access in the template
    answers_dict = {answer.question_id: answer for answer in answers}
    
    return render_template('teacher/view_quiz_attempt_details.html',
                         attempt=attempt,
                         quiz=quiz,
                         student=User.query.get(attempt.student_id),
                         answers_dict=answers_dict)

@teacher.route('/student/<int:student_id>/performance')
@login_required
@teacher_required
def student_performance(student_id):
    student = User.query.get_or_404(student_id)
    
    # Get all classes the teacher teaches
    teacher_classes = Class.query.filter_by(teacher_id=current_user.id).all()
    
    # Check if student is in any of the teacher's classes
    student_in_class = False
    for class_obj in teacher_classes:
        if student in class_obj.students:
            student_in_class = True
            break
    
    if not student_in_class:
        abort(403)  # Teacher can only view performance for their own students
    
    # Analyze student performance to identify weak topics
    performance_analysis = analyze_student_performance(student_id)
    
    # Get submission and quiz data
    submissions = []
    quiz_attempts = []
    
    for class_obj in teacher_classes:
        if student in class_obj.students:
            # Get assignments for this class
            for assignment in class_obj.assignments:
                submission = Submission.query.filter_by(
                    assignment_id=assignment.id,
                    student_id=student_id
                ).first()
                
                if submission:
                    submissions.append(submission)
            
            # Get quizzes for this class
            for quiz in class_obj.quizzes:
                attempts = QuizAttempt.query.filter_by(
                    quiz_id=quiz.id,
                    student_id=student_id
                ).order_by(QuizAttempt.started_at.desc()).all()
                
                for attempt in attempts:
                    quiz_attempts.append(attempt)
    
    return render_template('teacher/student_performance.html',
                         student=student,
                         submissions=submissions,
                         quiz_attempts=quiz_attempts,
                         performance_analysis=performance_analysis)

@teacher.route('/class/<int:class_id>/quiz/<int:quiz_id>/questions', methods=['GET', 'POST'])
@login_required
@teacher_required
def add_quiz_questions(class_id, quiz_id):
    class_obj = Class.query.get_or_404(class_id)
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Check if the current user is the teacher of this class
    if class_obj.teacher_id != current_user.id:
        abort(403)  # Forbidden
    
    # Check if the quiz belongs to this class
    if quiz.class_id != class_id:
        abort(400)  # Bad Request
    
    if request.method == 'POST':
        question_text = request.form.get('question_text')
        question_type = request.form.get('question_type')
        correct_answer = request.form.get('correct_answer')
        points = int(request.form.get('points', 1))
        
        if not all([question_text, question_type, correct_answer]):
            flash('All fields are required')
            return redirect(url_for('teacher.add_quiz_questions', class_id=class_id, quiz_id=quiz_id))
        
        # Create new question
        question = Question(
            question_text=question_text,
            question_type=question_type,
            correct_answer=correct_answer,
            points=points,
            quiz_id=quiz_id
        )
        db.session.add(question)
        
        # Handle multiple choice options
        if question_type == 'multiple_choice':
            options = request.form.getlist('options[]')
            if len(options) < 2:
                flash('Multiple choice questions must have at least 2 options')
                return redirect(url_for('teacher.add_quiz_questions', class_id=class_id, quiz_id=quiz_id))
            
            # Validate that correct answer is one of the options
            if correct_answer not in options:
                flash('Correct answer must be one of the options')
                return redirect(url_for('teacher.add_quiz_questions', class_id=class_id, quiz_id=quiz_id))
            
            # Add options
            for option_text in options:
                option = QuestionOption(
                    option_text=option_text,
                    question=question
                )
                db.session.add(option)
        
        db.session.commit()
        flash('Question added successfully!')
        
        # Check if we should add another question
        if 'add_another' in request.form:
            return redirect(url_for('teacher.add_quiz_questions', class_id=class_id, quiz_id=quiz_id))
        return redirect(url_for('teacher.class_details', class_id=class_id))
    
    return render_template('teacher/add_quiz_questions.html',
                         class_obj=class_obj,
                         quiz=quiz)

@teacher.route('/assignment/<int:assignment_id>/submissions')
@login_required
@teacher_required
def view_submissions(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    
    # Check if the current user is the teacher of this class
    if assignment.class_obj.teacher_id != current_user.id:
        abort(403)  # Forbidden
    
    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()
    
    return render_template('teacher/view_submissions.html',
                         assignment=assignment,
                         submissions=submissions)

@teacher.route('/assignment/<int:assignment_id>/submission/<int:submission_id>/grade', methods=['POST'])
@login_required
@teacher_required
def grade_submission(assignment_id, submission_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    submission = Submission.query.get_or_404(submission_id)
    
    # Check if the current user is the teacher of this class
    if assignment.class_obj.teacher_id != current_user.id:
        abort(403)  # Forbidden
    
    # Check if the submission belongs to the assignment
    if submission.assignment_id != assignment_id:
        abort(400)  # Bad Request
    
    grade = request.form.get('grade')
    feedback = request.form.get('feedback')
    
    if grade is not None:
        try:
            grade = int(grade)
            if 0 <= grade <= assignment.max_points:
                submission.grade = grade
                submission.feedback = feedback
                db.session.commit()
                flash('Grade updated successfully!')
            else:
                flash('Grade must be between 0 and maximum points')
        except ValueError:
            flash('Invalid grade value')
    
    return redirect(url_for('teacher.view_submissions', assignment_id=assignment_id))

@teacher.route('/class/<int:class_id>/create-assignment', methods=['GET', 'POST'])
@login_required
@teacher_required
def create_assignment(class_id):
    class_obj = Class.query.get_or_404(class_id)
    
    # Check if the current user is the teacher of this class
    if class_obj.teacher_id != current_user.id:
        abort(403)  # Forbidden
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%dT%H:%M')
        max_points = int(request.form.get('max_points'))
        
        if not all([title, description, due_date, max_points]):
            flash('All fields are required')
            return redirect(url_for('teacher.create_assignment', class_id=class_id))
        
        new_assignment = Assignment(
            title=title,
            description=description,
            due_date=due_date,
            max_points=max_points,
            class_id=class_id
        )
        
        db.session.add(new_assignment)
        db.session.commit()
        
        flash('Assignment created successfully!')
        return redirect(url_for('teacher.class_details', class_id=class_id))
    
    return render_template('teacher/create_assignment.html', class_obj=class_obj)

@teacher.route('/class/<int:class_id>/create-quiz', methods=['GET', 'POST'])
@login_required
@teacher_required
def create_quiz(class_id):
    class_obj = Class.query.get_or_404(class_id)
    
    # Check if the current user is the teacher of this class
    if class_obj.teacher_id != current_user.id:
        abort(403)  # Forbidden
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%dT%H:%M')
        time_limit = request.form.get('time_limit')
        
        if not all([title, due_date]):  # description and time_limit are optional
            flash('Title and due date are required')
            return redirect(url_for('teacher.create_quiz', class_id=class_id))
        
        new_quiz = Quiz(
            title=title,
            description=description,
            due_date=due_date,
            time_limit=int(time_limit) if time_limit else None,
            class_id=class_id
        )
        
        db.session.add(new_quiz)
        db.session.commit()
        
        flash('Quiz created successfully!')
        # Redirect to add questions page
        return redirect(url_for('teacher.add_quiz_questions', class_id=class_id, quiz_id=new_quiz.id))
    
    return render_template('teacher/create_quiz.html', class_obj=class_obj)

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

# API endpoints
@teacher.route('/api/classes', methods=['GET'])
@login_required
def get_classes():
    """API endpoint to get classes taught by the current teacher."""
    if not current_user.is_teacher():
        return jsonify({'error': 'Unauthorized'}), 403
    
    classes = current_user.classes_teaching.all()
    classes_data = [{'id': c.id, 'name': c.name} for c in classes]
    
    return jsonify(classes_data)

@teacher.route('/save-quiz', methods=['POST'])
@login_required
@teacher_required
def save_quiz():
    """Save an AI-generated quiz to the database."""
    try:
        # Get form data
        quiz_name = request.form.get('quiz_name')
        subject = request.form.get('subject')
        topic = request.form.get('topic')
        difficulty = request.form.get('difficulty')
        quiz_data = request.form.get('quiz_data')
        class_id = request.form.get('class_id')
        
        if not quiz_name or not quiz_data:
            flash('Missing required quiz information')
            return redirect(url_for('ai.quiz_creator'))
        
        # Parse the quiz data
        import json
        quiz_json = json.loads(quiz_data)
        
        # Create new quiz
        new_quiz = Quiz(
            title=quiz_name,
            description=f"Subject: {subject}, Topic: {topic}",
            class_id=class_id if class_id else None,
            created_at=datetime.now(),
            created_by=current_user.id,
            difficulty=difficulty
        )
        
        db.session.add(new_quiz)
        db.session.flush()  # Get the quiz ID
        
        # Add questions
        for i, q_data in enumerate(quiz_json.get('questions', [])):
            # Create question
            question = Question(
                quiz_id=new_quiz.id,
                question_text=q_data.get('question_text', ''),
                question_type='multiple_choice',
                points=1.0,  # Default points
                order=i+1
            )
            
            # Find correct answer
            correct_letter = q_data.get('correct_answer', 'A')
            correct_index = ord(correct_letter) - ord('A')
            options = q_data.get('options', [])
            
            if 0 <= correct_index < len(options):
                question.correct_answer = options[correct_index]
            
            # Add explanation if available
            if 'explanation' in q_data:
                question.explanation = q_data.get('explanation')
            
            db.session.add(question)
            db.session.flush()  # Get the question ID
            
            # Add options
            for j, option_text in enumerate(options):
                option = QuestionOption(
                    question_id=question.id,
                    option_text=option_text,
                    is_correct=(j == correct_index),
                    order=j+1
                )
                db.session.add(option)
        
        # Commit all changes
        db.session.commit()
        
        # Redirect based on whether a class was selected
        if class_id:
            flash(f'Quiz "{quiz_name}" has been saved to the class.')
            return redirect(url_for('teacher.class_details', class_id=class_id))
        else:
            flash(f'Quiz "{quiz_name}" has been saved.')
            return redirect(url_for('teacher.dashboard'))
            
    except Exception as e:
        db.session.rollback()
        print(f"Error saving quiz: {str(e)}")
        flash('An error occurred while saving the quiz. Please try again.')
        return redirect(url_for('ai.quiz_creator')) 