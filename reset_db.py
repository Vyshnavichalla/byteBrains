import os
from app import create_app, db
import models

# Create application and database context
app = create_app()
with app.app_context():
    # Drop all tables first
    db.drop_all()
    print("All existing tables dropped.")
    
    # Create database tables based on models
    db.create_all()
    print("Database tables created successfully!")
    
    # Create sample data
    # Create admin user
    admin = models.User(
        username='admin',
        email='admin@example.com',
        name='Admin User',
        role='admin'
    )
    admin.set_password('admin123')
    
    # Create a teacher
    teacher = models.User(
        username='teacher',
        email='teacher@example.com',
        name='John Smith',
        role='teacher'
    )
    teacher.set_password('teacher123')
    
    # Create a student
    student = models.User(
        username='student',
        email='student@example.com',
        name='Jane Doe',
        role='student'
    )
    student.set_password('student123')
    
    # Add sample users to database
    db.session.add_all([admin, teacher, student])
    db.session.commit()
    
    print("Sample users created!")
    print("Admin: username=admin, password=admin123")
    print("Teacher: username=teacher, password=teacher123")
    print("Student: username=student, password=student123")
    
    # Create a sample class
    sample_class = models.Class(
        name='Introduction to Python',
        description='Learn the basics of Python programming',
        join_code=models.Class.generate_join_code(),
        teacher_id=teacher.id
    )
    db.session.add(sample_class)
    db.session.commit()
    
    # Enroll the student in the class
    student.enrolled_classes.append(sample_class)
    db.session.commit()
    
    print(f"Sample class created: {sample_class.name} (Join Code: {sample_class.join_code})")
    print("Student enrolled in the sample class")
    
    # Create a sample assignment
    import datetime
    
    sample_assignment = models.Assignment(
        title='Hello World Program',
        description='Write a Python program that prints "Hello, World!" to the console.',
        due_date=datetime.datetime.now() + datetime.timedelta(days=7),
        max_points=10,
        class_id=sample_class.id
    )
    db.session.add(sample_assignment)
    db.session.commit()
    
    print(f"Sample assignment created: {sample_assignment.title}")
    
    print("Database setup complete!") 