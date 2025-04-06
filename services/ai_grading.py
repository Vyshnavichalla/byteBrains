import os
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from config import Config

# Initialize global variables
GEMINI_AVAILABLE = False
model = None

# Try to import Gemini, but make the service work even if it's not available
try:
    import google.generativeai as genai
    GEMINI_IMPORT_AVAILABLE = True
except ImportError:
    print("WARNING: Google GenerativeAI package not installed. Using fallback grading methods.")
    GEMINI_IMPORT_AVAILABLE = False

# Try to load environment variables if dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("WARNING: python-dotenv not installed. Environment variables must be set manually.")

# Try to initialize Gemini client if the import was successful
if GEMINI_IMPORT_AVAILABLE:
    try:
        api_key = Config.GEMINI_API_KEY
        if api_key and api_key != "your_gemini_api_key_here":
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.0-flash')
            GEMINI_AVAILABLE = True
            print("Gemini API initialized successfully with gemini-2.0-flash model.")
        else:
            print("WARNING: No valid Gemini API key found. Using fallback grading methods.")
    except Exception as e:
        print(f"ERROR initializing Gemini client: {str(e)}")
        GEMINI_AVAILABLE = False

def grade_assignment(submission_text, assignment_description, max_points, rubric=None):
    """
    Grade an assignment submission using AI and generate feedback.
    
    Args:
        submission_text: The student's submitted text
        assignment_description: The description/prompt of the assignment
        max_points: Maximum points possible
        rubric: Optional grading rubric
    
    Returns:
        dict: Contains grade, feedback, and weak_topics
    """
    # If Gemini is not available, use fallback grading
    if not GEMINI_AVAILABLE:
        return fallback_grade_assignment(submission_text, assignment_description, max_points)
    
    # Prepare prompt for AI grading
    prompt = f"""
    Assignment: {assignment_description}
    
    Student Submission: {submission_text}
    
    Maximum Points: {max_points}
    """
    
    if rubric:
        prompt += f"\nRubric: {rubric}"
    
    prompt += """
    
    Please grade this assignment by:
    1. Assigning a score (out of the maximum points)
    2. Providing detailed feedback on strengths and weaknesses
    3. Identifying specific topics/concepts where the student needs improvement
    
    Format your response as:
    Score: [numerical score]
    Feedback: [detailed feedback]
    Weak Topics: [comma-separated list of weak topics]
    """
    
    try:
        # Call Gemini API for grading
        response = model.generate_content(prompt)
        
        # Parse response
        content = response.text
        
        # Extract score, feedback, and weak topics
        result = {
            "grade": None,
            "feedback": "",
            "weak_topics": []
        }
        
        for line in content.split("\n"):
            if line.startswith("Score:"):
                try:
                    score_text = line.replace("Score:", "").strip()
                    # Handle cases like "8/10" or just "8"
                    if "/" in score_text:
                        score = float(score_text.split("/")[0])
                    else:
                        score = float(score_text)
                    result["grade"] = min(score, max_points)  # Ensure score doesn't exceed max_points
                except ValueError:
                    result["grade"] = max_points * 0.7  # Default if parsing fails
            
            elif line.startswith("Feedback:"):
                result["feedback"] = line.replace("Feedback:", "").strip()
                
            elif line.startswith("Weak Topics:"):
                topics = line.replace("Weak Topics:", "").strip()
                result["weak_topics"] = [topic.strip() for topic in topics.split(",")]
        
        # If feedback is empty, use the entire content minus the score and weak topics lines
        if not result["feedback"]:
            result["feedback"] = "\n".join([
                line for line in content.split("\n") 
                if not line.startswith("Score:") and not line.startswith("Weak Topics:")
            ])
            
        # If no grade was extracted, estimate based on semantic similarity
        if result["grade"] is None:
            result["grade"] = estimate_grade_by_similarity(submission_text, assignment_description, max_points)
            
        return result
        
    except Exception as e:
        # Fallback to similarity-based grading if API fails
        print(f"AI grading error: {str(e)}")
        return fallback_grade_assignment(submission_text, assignment_description, max_points)

def fallback_grade_assignment(submission_text, assignment_description, max_points):
    """Fallback method when AI grading is not available"""
    grade = estimate_grade_by_similarity(submission_text, assignment_description, max_points)
    
    # Generate simple feedback based on the grade
    percentage = (grade / max_points) * 100
    
    if percentage >= 90:
        feedback = "Excellent work! The submission thoroughly addresses the assignment requirements."
    elif percentage >= 80:
        feedback = "Good work! The submission covers most of the key aspects of the assignment."
    elif percentage >= 70:
        feedback = "Satisfactory work. The submission addresses the basic requirements but could be improved."
    elif percentage >= 60:
        feedback = "The submission partially addresses the requirements but needs significant improvement."
    else:
        feedback = "The submission does not adequately address the assignment requirements. Please review the assignment description and try again."
    
    # Generate some generic weak topics based on the grade
    if percentage < 70:
        weak_topics = ["content comprehension", "assignment requirements", "attention to detail"]
    else:
        weak_topics = []
        
    return {
        "grade": grade,
        "feedback": feedback,
        "weak_topics": weak_topics
    }

def grade_quiz_answer(student_answer, correct_answer, question_text, points):
    """
    Grade a single quiz answer using AI.
    
    Args:
        student_answer: Student's answer text
        correct_answer: Correct answer text
        question_text: The question text
        points: Points for this question
    
    Returns:
        dict: Contains is_correct, points_earned, and feedback
    """
    # Exact match for simple answers (case-insensitive)
    if student_answer.lower() == correct_answer.lower():
        return {
            "is_correct": True,
            "points_earned": points,
            "feedback": "Correct answer!"
        }
    
    # Check if it's a short or simple answer
    if len(student_answer) < 20 or len(correct_answer) < 20:
        # For short answers, use stricter grading
        similarity = get_text_similarity(student_answer, correct_answer)
        
        if similarity > 0.9:
            return {
                "is_correct": True,
                "points_earned": points,
                "feedback": "Correct answer!"
            }
        else:
            return {
                "is_correct": False,
                "points_earned": 0,
                "feedback": f"Incorrect. The correct answer is: {correct_answer}"
            }
    
    # For longer, more complex answers, use AI grading if available
    if GEMINI_AVAILABLE:
        try:
            prompt = f"""
            Question: {question_text}
            
            Correct Answer: {correct_answer}
            
            Student Answer: {student_answer}
            
            Maximum Points: {points}
            
            Please assess this answer by:
            1. Determining if it's correct (Yes/No)
            2. Assigning points (0 to {points})
            3. Providing brief feedback
            
            Format your response as:
            Correct: [Yes/No]
            Points: [points earned]
            Feedback: [brief feedback]
            """
            
            response = model.generate_content(prompt)
            content = response.text
            
            result = {
                "is_correct": False,
                "points_earned": 0,
                "feedback": "Incorrect answer."
            }
            
            for line in content.split("\n"):
                if line.startswith("Correct:"):
                    correct_text = line.replace("Correct:", "").strip().lower()
                    result["is_correct"] = correct_text in ["yes", "true", "correct"]
                
                elif line.startswith("Points:"):
                    try:
                        points_text = line.replace("Points:", "").strip()
                        result["points_earned"] = min(float(points_text), points)
                    except ValueError:
                        result["points_earned"] = 0
                
                elif line.startswith("Feedback:"):
                    result["feedback"] = line.replace("Feedback:", "").strip()
            
            # If feedback is empty, provide generic feedback
            if not result["feedback"]:
                if result["is_correct"]:
                    result["feedback"] = "Correct answer!"
                else:
                    result["feedback"] = f"Incorrect. The correct answer is: {correct_answer}"
                    
            return result
            
        except Exception as e:
            # Fallback to similarity-based grading if API fails
            print(f"AI grading error: {str(e)}")
            return fallback_grade_quiz_answer(student_answer, correct_answer, points)
    else:
        # Use fallback grading when Gemini is not available
        return fallback_grade_quiz_answer(student_answer, correct_answer, points)

def fallback_grade_quiz_answer(student_answer, correct_answer, points):
    """Fallback method for grading quiz answers when AI is not available"""
    similarity = get_text_similarity(student_answer, correct_answer)
    
    # Determine correctness based on similarity threshold
    is_correct = similarity > 0.7
    
    # Calculate points - full points if correct, partial based on similarity if not
    points_earned = points if is_correct else round(similarity * points, 1)
    
    # Generate feedback
    if is_correct:
        feedback = "Correct answer!"
    else:
        feedback = f"Partially correct. The correct answer is: {correct_answer}"
        
    return {
        "is_correct": is_correct,
        "points_earned": points_earned,
        "feedback": feedback
    }

def analyze_student_performance(student_id, class_id=None):
    """
    Analyze a student's performance across assignments and quizzes
    to identify weak topics.
    
    Args:
        student_id: The student's ID
        class_id: Optional class ID to limit analysis to a specific class
    
    Returns:
        dict: Contains weak_topics with confidence scores and recommendations
    """
    from models import Submission, QuizAttempt, QuizAnswer, Assignment, Quiz, Question
    
    # Get all student submissions
    query = Submission.query.filter_by(student_id=student_id)
    if class_id:
        query = query.join(Assignment).filter(Assignment.class_id == class_id)
    submissions = query.all()
    
    # Get all quiz attempts
    query = QuizAttempt.query.filter_by(student_id=student_id)
    if class_id:
        query = query.join(Quiz).filter(Quiz.class_id == class_id)
    attempts = query.all()
    
    # Extract weak topics from submissions and quiz answers
    topics_data = []
    
    # From assignments
    for submission in submissions:
        assignment = submission.assignment
        max_points = assignment.max_points
        
        if submission.grade:
            performance = submission.grade / max_points
            # Consider topics as weak if performance is below 70%
            if performance < 0.7 and submission.feedback:
                # Try to extract topics from weak_topics field or use the assignment title
                if submission.weak_topics:
                    for topic in submission.weak_topics.split(','):
                        topics_data.append({
                            "topic": topic.strip(),
                            "score": performance,
                            "type": "assignment"
                        })
                else:
                    topics_data.append({
                        "topic": assignment.title,
                        "score": performance,
                        "type": "assignment"
                    })
    
    # From quizzes
    for attempt in attempts:
        quiz = attempt.quiz
        
        if attempt.score is not None and quiz.total_points > 0:
            performance = attempt.score / quiz.total_points
            
            # Get incorrect answers to identify weak topics
            incorrect_answers = QuizAnswer.query.filter_by(
                attempt_id=attempt.id,
                is_correct=False
            ).all()
            
            for answer in incorrect_answers:
                question = Question.query.get(answer.question_id)
                if question:
                    topics_data.append({
                        "topic": question.question_text,
                        "score": 0,  # Completely incorrect
                        "type": "quiz"
                    })
    
    # Aggregate topics by similarity
    if topics_data:
        # Extract all topics
        all_topics = [data["topic"] for data in topics_data]
        
        # Create clusters of similar topics
        clustered_topics = cluster_similar_topics(all_topics)
        
        # Calculate average score for each cluster
        weak_topics_analysis = []
        for cluster_name, topic_indices in clustered_topics.items():
            cluster_scores = [topics_data[i]["score"] for i in topic_indices]
            avg_score = sum(cluster_scores) / len(cluster_scores)
            
            weak_topics_analysis.append({
                "topic": cluster_name,
                "confidence": 1 - avg_score,  # Convert score to confidence (1 = very weak, 0 = strong)
                "occurrences": len(topic_indices),
                "recommendation": generate_study_recommendation(cluster_name)
            })
        
        # Sort by confidence (highest first)
        weak_topics_analysis.sort(key=lambda x: x["confidence"], reverse=True)
        
        return {
            "weak_topics": weak_topics_analysis[:5]  # Return top 5 weak topics
        }
    
    return {"weak_topics": []}

def generate_study_recommendation(topic):
    """Generate a study recommendation for a weak topic."""
    if GEMINI_AVAILABLE:
        try:
            prompt = f"""
            A student is struggling with the topic: "{topic}"
            
            Please provide a brief, helpful study recommendation that includes:
            1. One resource they could use (book, website, or video)
            2. One practical exercise they could do to improve
            
            Keep it under 100 words.
            """
            
            response = model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            print(f"Error generating recommendation: {str(e)}")
            return fallback_recommendation(topic)
    else:
        return fallback_recommendation(topic)

def fallback_recommendation(topic):
    """Generate a basic recommendation when AI is not available"""
    # Create a generic but helpful recommendation based on the topic
    topic_lower = topic.lower()
    
    if any(term in topic_lower for term in ["math", "calculation", "equation", "formula"]):
        return f"To improve in {topic}, visit Khan Academy for free tutorials and practice problems. Work through example problems step-by-step with explanations to build confidence in this area."
    
    elif any(term in topic_lower for term in ["write", "essay", "grammar", "composition"]):
        return f"For {topic}, check Purdue OWL Writing Lab website for guidelines and resources. Practice by writing short paragraphs daily and asking peers to review your work."
    
    elif any(term in topic_lower for term in ["code", "programming", "algorithm"]):
        return f"To strengthen {topic} skills, use Codecademy or freeCodeCamp for interactive lessons. Build a small project applying these concepts to reinforce your understanding."
    
    else:
        return f"For {topic}, find targeted resources on YouTube tutorials or educational websites. Create flashcards for key concepts and practice with regular review sessions and applied exercises."

def get_text_similarity(text1, text2):
    """Calculate cosine similarity between two texts."""
    if not text1 or not text2:
        return 0.0
        
    vectorizer = TfidfVectorizer()
    try:
        tfidf_matrix = vectorizer.fit_transform([text1, text2])
        return cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
    except:
        # Fallback for very short or identical texts
        if text1.lower() == text2.lower():
            return 1.0
        return 0.0

def estimate_grade_by_similarity(submission_text, assignment_description, max_points):
    """Estimate a grade based on text similarity when AI grading fails."""
    base_similarity = get_text_similarity(submission_text, assignment_description)
    
    # Apply some adjustments to make the grading more realistic
    # A perfect similarity would be 1.0, but we want to be a bit stricter
    adjusted_similarity = base_similarity * 0.8
    
    # Calculate grade - minimum 40% if they submitted something relevant
    if adjusted_similarity > 0.1:
        grade = max(0.4 * max_points, adjusted_similarity * max_points)
    else:
        grade = 0
        
    return min(round(grade, 1), max_points)

def cluster_similar_topics(topics, threshold=0.6):
    """Group similar topics into clusters."""
    if not topics:
        return {}
        
    # Calculate similarity matrix
    vectorizer = TfidfVectorizer()
    try:
        tfidf_matrix = vectorizer.fit_transform(topics)
        similarity_matrix = cosine_similarity(tfidf_matrix)
    except:
        # Fallback for very short texts
        return {topics[0]: list(range(len(topics)))}
    
    # Create clusters
    clusters = {}
    used_indices = set()
    
    for i in range(len(topics)):
        if i in used_indices:
            continue
            
        cluster_indices = [i]
        used_indices.add(i)
        
        # Find similar topics
        for j in range(len(topics)):
            if j not in used_indices and similarity_matrix[i, j] > threshold:
                cluster_indices.append(j)
                used_indices.add(j)
        
        # Use the first topic as the cluster name
        clusters[topics[i]] = cluster_indices
    
    return clusters 