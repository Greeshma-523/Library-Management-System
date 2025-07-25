from flask_mail import Message
from app import mail, app
from flask import render_template

def send_notification_email(to_email, subject, template_name, **context):
    """
    Sends an email using Flask-Mail with a rendered HTML template.

    :param to_email: Recipient email address
    :param subject: Subject of the email
    :param template_name: Name of the HTML template (in templates folder)
    :param context: Variables to pass into the template rendering
    """
    with app.app_context():
        msg = Message(subject,
                      sender=app.config['MAIL_USERNAME'],
                      recipients=[to_email])
        msg.html = render_template(template_name, **context)
        mail.send(msg)
