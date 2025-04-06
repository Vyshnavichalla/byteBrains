from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import random
import string
from datetime import datetime

db = SQLAlchemy()

# Association tables
student_classes = db.Table('student_classes',
    db.Column('student_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('class_id', db.Integer, db.ForeignKey('class.id'), primary_key=True)
)

# Association table for student-class enrollments
enrollments = db.Table('enrollments',
    db.Column('student_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('class_id', db.Integer, db.ForeignKey('class.id'), primary_key=True)
)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'student', 'teacher', or 'admin'
    
    # Relationships for students
    enrolled_classes = db.relationship('Class', secondary=enrollments, backref=db.backref('students', lazy='dynamic'), lazy='dynamic')
    submissions = db.relationship('Submission', backref='student', lazy=True)
    quiz_attempts = db.relationship('QuizAttempt', backref='student', lazy=True)
    
    # Relationship for teachers
    classes_teaching = db.relationship('Class', backref='teacher', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_teacher(self):
        return self.role == 'teacher'
    
    def is_student(self):
        return self.role == 'student'
    
    def is_admin(self):
        return self.role == 'admin'

class Class(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    join_code = db.Column(db.String(6), unique=True, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    assignments = db.relationship('Assignment', backref='class_obj', lazy=True)
    quizzes = db.relationship('Quiz', backref='class', lazy=True)

    @staticmethod
    def generate_join_code():
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not Class.query.filter_by(join_code=code).first():
                return code

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    max_points = db.Column(db.Integer, nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    
    # Define relationship from Assignment to Submission without backref
    submissions = db.relationship('Submission', back_populates='assignment', lazy=True)

    def get_submission(self, student):
        return Submission.query.filter_by(
            student_id=student.id,
            assignment_id=self.id
        ).first()

    @property
    def class_obj(self):
        return Class.query.get(self.class_id)

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    submission_text = db.Column(db.Text, nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    grade = db.Column(db.Float)
    feedback = db.Column(db.Text)
    weak_topics = db.Column(db.Text)  # Comma-separated list of weak topics
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Define relationship from Submission to Assignment with back_populates
    assignment = db.relationship('Assignment', back_populates='submissions')

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    due_date = db.Column(db.DateTime, nullable=True)  # Make nullable since AI-generated quizzes may not have a due date initially
    time_limit = db.Column(db.Integer)  # in minutes
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    difficulty = db.Column(db.String(20), default='medium')  # For AI-generated quizzes
    questions_json = db.Column(db.Text)  # Store AI-generated questions as JSON
    
    # Relationships
    questions = db.relationship('Question', backref='quiz', lazy=True)
    attempts = db.relationship('QuizAttempt', backref='quiz', lazy=True)
    
    @property
    def total_points(self):
        """Calculate the total points possible for this quiz."""
        return sum(question.points for question in self.questions)
    
    @property
    def class_obj(self):
        """For backwards compatibility with existing code."""
        from models import Class  # Import here to avoid circular imports
        return Class.query.get(self.class_id)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # 'multiple_choice', 'true_false', etc.
    correct_answer = db.Column(db.Text, nullable=False)
    points = db.Column(db.Integer, nullable=False, default=1)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    
    # For multiple choice questions
    options = db.relationship('QuestionOption', backref='question', lazy=True)

class QuestionOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    option_text = db.Column(db.Text, nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)

class QuizAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    score = db.Column(db.Integer)
    
    # Foreign Keys
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships - the backref is defined in the User model
    answers = db.relationship('QuizAnswer', backref='attempt', lazy=True)

    def calculate_score(self):
        total_points = sum(q.points for q in self.quiz.questions)
        earned_points = sum(a.points_earned or 0 for a in self.answers)
        self.score = earned_points
        return self.score

class QuizAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_answer = db.Column(db.Text, nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    points_earned = db.Column(db.Float, default=0)
    feedback = db.Column(db.Text)  # Feedback on this answer
    attempt_id = db.Column(db.Integer, db.ForeignKey('quiz_attempt.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    
    # Relationships
    question = db.relationship('Question', backref=db.backref('answers', lazy=True)) 