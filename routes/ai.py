from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
import google.generativeai as genai
from flask_login import login_required, current_user
from config import Config
import markdown
from models import db, Assignment, Submission, Quiz, QuizAttempt, User, Class

ai = Blueprint('ai', __name__, url_prefix='/ai')

# Configure the Gemini API
try:
    api_key = Config.GEMINI_API_KEY
    if api_key and api_key.strip():
        genai.configure(api_key=api_key)
        try:
            # Initialize with Gemini 2.0 Flash model
            model = genai.GenerativeModel('gemini-2.0-flash')
            # Test the model with a simple prompt
            test_response = model.generate_content("Hello")
            if test_response and hasattr(test_response, 'text'):
                GEMINI_AVAILABLE = True
                print(f"Gemini API initialized successfully with gemini-2.0-flash model")
            else:
                GEMINI_AVAILABLE = False
                model = None
                print("Gemini model failed to generate content.")
        except Exception as model_error:
            GEMINI_AVAILABLE = False
            model = None
            print(f"ERROR initializing Gemini model: {model_error}")
    else:
        GEMINI_AVAILABLE = False
        model = None
        print("No Gemini API key provided.")
except Exception as e:
    GEMINI_AVAILABLE = False
    model = None
    print(f"ERROR initializing Gemini API: {e}")

@ai.route('/chat')
@login_required
def chat_interface():
    """Render the AI chat interface."""
    return render_template('ai_chat.html')

@ai.route('/generate', methods=['POST'])
@login_required
def generate():
    """Generate AI response."""
    try:
        data = request.get_json()
        prompt = data.get('prompt')
        
        if not prompt:
            return jsonify({'error': 'No prompt provided', 'status': 'error'}), 400
        
        # Add debug information
        print(f"[DEBUG] Processing prompt: '{prompt}'")
        print(f"[DEBUG] Gemini Available: {GEMINI_AVAILABLE}, Model exists: {model is not None}")
        
        # If Gemini API is not available, inform the user
        if not GEMINI_AVAILABLE or not model:
            print(f"[DEBUG] Gemini API not available")
            return jsonify({
                'response': "I'm sorry, but I'm currently unable to process your request. Please check your internet connection or try again later.",
                'status': 'success'
            })

        # Add context about the educational setting and instructions to avoid code examples
        context = f"""You are an AI teaching assistant helping a {'teacher' if current_user.is_teacher() else 'student'} 
in an educational platform. Provide helpful and educational responses.

IMPORTANT INSTRUCTIONS:
1. Answer directly without showing example input/output patterns
2. Do not include expected user prompts or system responses in your answers
3. Do not format your responses as code conversations
4. Keep explanations clear and factual without imaginary dialog

USER INPUT: {prompt}
"""
        
        # Generate response using Gemini
        print(f"[DEBUG] Sending to Gemini API")
        try:
            # Configure generation parameters
            generation_config = {
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 40,
                "max_output_tokens": 2048,
            }
            
            # Safety settings
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
            
            response = model.generate_content(
                context,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            if not response or not hasattr(response, 'text') or not response.text or response.text.strip() == "":
                print("[DEBUG] No valid response received from Gemini API")
                return jsonify({
                    'response': "I'm sorry, but I couldn't generate a response. Please try rephrasing your message.",
                    'status': 'success'
                })
            
            # Process the response to remove any example patterns
            processed_response = clean_response(response.text)
            
            print(f"[DEBUG] Gemini API response received, length: {len(processed_response)}")
            print(f"[DEBUG] First 30 chars of response: {processed_response[:30]}...")
            
            # Return the Gemini response
            return jsonify({
                'response': processed_response,
                'status': 'success'
            })
            
        except Exception as gemini_error:
            print(f"[DEBUG] Error in Gemini API call: {str(gemini_error)}")
            print(f"[DEBUG] Error type: {type(gemini_error).__name__}")
            return jsonify({
                'response': "I apologize, but I encountered an error while processing your request. Please try again later.",
                'status': 'success'
            })
    
    except Exception as e:
        print(f"[DEBUG] Error in AI generation: {str(e)}")
        return jsonify({
            'response': "I'm sorry, but I encountered an error processing your request. Please try again with a different message.",
            'status': 'success'
        })

def clean_response(response_text):
    """Remove any patterns that look like example input/output or code conversations."""
    # Remove lines that look like input prompts
    lines = response_text.split('\n')
    filtered_lines = []
    
    skip_next = False
    for i, line in enumerate(lines):
        line_lower = line.strip().lower()
        
        # Skip lines that look like input prompts
        if (line_lower.startswith('user:') or 
            line_lower.startswith('student:') or 
            line_lower.startswith('input:') or 
            line_lower.startswith('> ') or
            line_lower.startswith('>>') or
            line_lower.startswith('$') or
            'expected output' in line_lower or
            'example input' in line_lower):
            skip_next = True
            continue
            
        # Skip lines that look like AI/system responses
        if (line_lower.startswith('ai:') or 
            line_lower.startswith('assistant:') or 
            line_lower.startswith('system:') or
            line_lower.startswith('output:') or
            line_lower.startswith('response:')):
            skip_next = True
            continue
            
        # If we decided to skip this line based on the previous line, continue
        if skip_next:
            skip_next = False
            if not line.strip():  # If it's an empty line, reset skip_next
                skip_next = False
            continue
            
        filtered_lines.append(line)
    
    # Join the filtered lines back together
    cleaned_text = '\n'.join(filtered_lines)
    
    # Remove any remaining code conversation markers
    markers_to_remove = [
        "Example:", "Input:", "Output:", 
        "Expected Input:", "Expected Output:",
        "User:", "AI:", "System:"
    ]
    
    for marker in markers_to_remove:
        cleaned_text = cleaned_text.replace(marker, "")
    
    return cleaned_text.strip()

@ai.route('/tutor/<subject>')
@login_required
def tutor(subject):
    """Access a specialized tutor for a specific subject."""
    subjects = {
        'math': 'Mathematics',
        'science': 'Science',
        'english': 'English',
        'history': 'History',
        'programming': 'Programming'
    }
    
    if subject not in subjects:
        flash('Subject not available. Please choose from the available subjects.')
        return redirect(url_for('ai.tutoring_hub'))
    
    return render_template('ai_tutor.html', subject=subjects[subject])

@ai.route('/tutoring-hub')
@login_required
def tutoring_hub():
    """Landing page for AI tutoring services."""
    return render_template('tutoring_hub.html')

@ai.route('/explainer')
@login_required
def concept_explainer():
    """Render the concept explainer page."""
    return render_template('concept_explainer.html')

@ai.route('/explain-concept', methods=['POST'])
@login_required
def explain_concept():
    """Generate an explanation for a concept."""
    try:
        # Check if request is JSON or form data
        if request.is_json:
            data = request.get_json()
            concept = data.get('concept')
            difficulty = data.get('difficulty', 'intermediate')
        else:
            concept = request.form.get('concept')
            difficulty = request.form.get('difficulty', 'intermediate')
        
        if not concept:
            flash('Please provide a concept to explain.')
            return redirect(url_for('ai.concept_explainer'))
        
        # If Gemini API is not available, inform the user
        if not GEMINI_AVAILABLE or not model:
            flash('The AI service is currently unavailable. Please try again later.')
            return redirect(url_for('ai.concept_explainer'))
        
        # Prepare prompt for Gemini
        education_levels = {
            'beginner': 'elementary school student (ages 8-11)',
            'intermediate': 'middle school student (ages 12-14)',
            'advanced': 'high school student (ages 15-18)',
            'expert': 'undergraduate college student'
        }
        
        audience = education_levels.get(difficulty, 'middle school student')
        
        prompt = f"""
        Please explain the concept of "{concept}" to a {audience}.
        
        Your explanation should:
        1. Be clear, accurate, and educational
        2. Include key points and principles
        3. Provide examples where appropriate
        4. Be structured with proper paragraphs
        5. Avoid unnecessary jargon
        
        Format your response as an educational explanation, not as a chat message.
        Do not use dialog or conversation formatting.
        """
        
        # Generate response using Gemini
        try:
            generation_config = {
                "temperature": 0.5,  # Lower for more factual responses
                "top_p": 0.8,
                "top_k": 40,
                "max_output_tokens": 4000,  # Higher for detailed explanations
            }
            
            response = model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            if not response or not hasattr(response, 'text') or not response.text:
                flash("I couldn't generate an explanation. Please try a different concept.")
                return redirect(url_for('ai.concept_explainer'))
            
            # Convert the explanation to HTML for better formatting
            explanation_html = markdown.markdown(response.text)
            
            # Render the explanation page
            return render_template(
                'concept_explanation.html',
                concept=concept,
                difficulty=difficulty,
                explanation=explanation_html
            )
            
        except Exception as e:
            print(f"Error generating explanation: {str(e)}")
            flash(f"I encountered an error while explaining '{concept}'. Please try again.")
            return redirect(url_for('ai.concept_explainer'))
    
    except Exception as e:
        print(f"Error in concept explanation: {str(e)}")
        flash("I encountered a technical error. Please try again later.")
        return redirect(url_for('ai.concept_explainer'))

@ai.route('/generate-study-plan', methods=['GET', 'POST'])
@login_required
def generate_study_plan():
    """Render the study plan generator page or create a study plan."""
    if request.method == 'GET':
        return render_template('generate_study_plan.html')
    
    try:
        # Check if request is JSON or form data
        if request.is_json:
            data = request.get_json()
            subject = data.get('subject')
            topics = data.get('topics')
            duration = data.get('duration', '1 week')
            goals = data.get('goals', '')
        else:
            subject = request.form.get('subject')
            topics = request.form.get('topics')
            duration = request.form.get('duration', '1 week')
            goals = request.form.get('goals', '')
        
        if not subject or not topics:
            if request.is_json:
                return jsonify({'error': 'Subject and topics are required', 'status': 'error'}), 400
            else:
                flash('Please provide both subject and topics for your study plan.')
                return redirect(url_for('ai.generate_study_plan'))
        
        if isinstance(topics, list):
            topics = ", ".join(topics)
        
        # If Gemini API is not available, inform the user
        if not GEMINI_AVAILABLE or not model:
            if request.is_json:
                return jsonify({
                    'error': 'The AI service is currently unavailable.',
                    'status': 'error'
                }), 503
            else:
                flash('The AI service is currently unavailable. Please try again later.')
                return redirect(url_for('ai.generate_study_plan'))
        
        # Prepare prompt for Gemini
        prompt = f"""
        Please create a structured study plan for the subject: {subject}
        
        Topics to cover: {topics}
        
        Duration: {duration}
        
        Student's goals: {goals}
        
        The study plan should include:
        1. A schedule breaking down what to study each day
        2. Specific learning activities for each topic
        3. Recommended resources (textbooks, videos, practice problems)
        4. Short assessment activities to track progress
        
        Format the plan clearly with sections and bullet points where appropriate.
        """
        
        # Generate response using Gemini
        try:
            generation_config = {
                "temperature": 0.5,
                "top_p": 0.8,
                "top_k": 40,
                "max_output_tokens": 4000,
            }
            
            response = model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            if not response or not hasattr(response, 'text') or not response.text:
                if request.is_json:
                    return jsonify({
                        'error': 'Failed to generate study plan',
                        'status': 'error'
                    }), 500
                else:
                    flash("I couldn't generate a study plan. Please try different parameters.")
                    return redirect(url_for('ai.generate_study_plan'))
            
            # If JSON request, return JSON response
            if request.is_json:
                return jsonify({
                    'plan': response.text,
                    'status': 'success'
                })
            
            # Otherwise, render the study plan page
            study_plan_html = markdown.markdown(response.text)
            return render_template(
                'study_plan.html',
                subject=subject,
                topics=topics,
                duration=duration,
                plan=study_plan_html
            )
            
        except Exception as e:
            print(f"Error generating study plan: {str(e)}")
            if request.is_json:
                return jsonify({
                    'error': f"Error generating study plan: {str(e)}",
                    'status': 'error'
                }), 500
            else:
                flash("I encountered an error generating your study plan. Please try again.")
                return redirect(url_for('ai.generate_study_plan'))
    
    except Exception as e:
        print(f"Error in study plan generation: {str(e)}")
        if request.is_json:
            return jsonify({
                'error': f"Error in study plan generation: {str(e)}",
                'status': 'error'
            }), 500
        else:
            flash("I encountered a technical error. Please try again later.")
            return redirect(url_for('ai.generate_study_plan'))

@ai.route('/homework-help')
@login_required
def homework_help():
    """Render the homework help page."""
    return render_template('homework_help.html')

@ai.route('/quiz-creator', methods=['GET', 'POST'])
@login_required
def quiz_creator():
    """AI-powered quiz creator for teachers."""
    if not current_user.is_teacher():
        flash("Access denied. Only teachers can use the quiz creator.")
        return redirect(url_for('main.index'))
    
    # Get teacher's classes for the dropdown
    classes = Class.query.filter_by(teacher_id=current_user.id).all()
    
    if request.method == 'GET':
        return render_template('quiz_creator.html', classes=classes)
    
    try:
        # Get form data for creating a quiz
        subject = request.form.get('subject')
        topic = request.form.get('topic')
        difficulty = request.form.get('difficulty', 'intermediate')
        num_questions = request.form.get('num_questions', 5)
        class_id = request.form.get('class_id')
        
        # Validate input
        try:
            num_questions = int(num_questions)
            if num_questions < 1 or num_questions > 10:
                num_questions = 5  # Default to 5 if invalid
        except:
            num_questions = 5
        
        if not subject or not topic:
            flash('Please provide both subject and topic for the quiz.')
            return redirect(url_for('ai.quiz_creator'))
        
        # If Gemini API is not available, inform the user
        if not GEMINI_AVAILABLE or not model:
            flash('The AI service is currently unavailable. Please try again later.')
            return redirect(url_for('ai.quiz_creator'))
        
        # Prepare prompt for Gemini
        prompt = f"""
        Create a quiz on the topic of "{topic}" for the subject "{subject}" with {num_questions} questions.
        
        Difficulty level: {difficulty}
        
        For each question:
        1. Create a clear, concise question
        2. Provide 4 answer options (A, B, C, D)
        3. Indicate the correct answer
        4. Include a brief explanation for the correct answer
        
        Format your response in the following JSON structure:
        {{
            "quiz_title": "Title of the Quiz",
            "questions": [
                {{
                    "question_text": "The question text",
                    "options": ["Option A", "Option B", "Option C", "Option D"],
                    "correct_answer": "A", 
                    "explanation": "Explanation for why this is correct"
                }},
                // More questions...
            ]
        }}
        
        Ensure the questions are educational, accurate, and appropriate for the specified difficulty level.
        """
        
        # Generate response using Gemini
        try:
            generation_config = {
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40,
                "max_output_tokens": 4000,
            }
            
            response = model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            if not response or not hasattr(response, 'text') or not response.text:
                flash("I couldn't generate a quiz. Please try different parameters.")
                return redirect(url_for('ai.quiz_creator'))
            
            # Return the quiz creation page with the generated quiz
            return render_template(
                'quiz_preview.html',
                quiz_data=response.text,
                subject=subject,
                topic=topic,
                difficulty=difficulty,
                classes=classes,
                class_id=class_id
            )
            
        except Exception as e:
            print(f"Error generating quiz: {str(e)}")
            flash(f"I encountered an error while creating your quiz. Please try again.")
            return redirect(url_for('ai.quiz_creator'))
    
    except Exception as e:
        print(f"Error in quiz creation: {str(e)}")
        flash("I encountered a technical error. Please try again later.")
        return redirect(url_for('ai.quiz_creator'))

@ai.route('/assignment-idea-generator', methods=['GET', 'POST'])
@login_required
def assignment_idea_generator():
    """Generate assignment ideas for teachers."""
    if not current_user.is_teacher():
        flash("Access denied. Only teachers can use the assignment idea generator.")
        return redirect(url_for('main.index'))
        
    return render_template('assignment_idea_generator.html')

# Add a simple error handler
@ai.errorhandler(Exception)
def handle_error(e):
    print(f"AI route error: {str(e)}")
    return render_template('error.html', message="An error occurred in the AI system."), 500
