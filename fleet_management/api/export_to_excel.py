from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.http import JsonResponse, HttpResponse
from rest_framework.decorators import api_view
from ..models import Trajectory
from celery import shared_task
from openpyxl import Workbook
from django.core.files.base import ContentFile
from ..lib import Smtp
import logging
from datetime import datetime
import os
from io import BytesIO

@swagger_auto_schema(method='get', manual_parameters=[
    openapi.Parameter('taxi_id', openapi.IN_QUERY, description="Taxi ID", type=openapi.TYPE_STRING),
    openapi.Parameter('date', openapi.IN_QUERY, description="Date", type=openapi.TYPE_STRING),
    openapi.Parameter('to_emails', openapi.IN_QUERY, description="Comma separated list of emails", type=openapi.TYPE_STRING),
])
@api_view(['GET'])
def export_to_excel(request):
    query_params = request.query_params
    taxi_id = query_params.get('taxi_id')
    date = query_params.get('date')
    to_emails = query_params.get('to_emails')

    file_identifier = f"{taxi_id}_{date}"

    generate_excel_task.delay(taxi_id, date, file_identifier, to_emails)

    return JsonResponse({'message': 'Excel generation started.', 'file_identifier': file_identifier})

@shared_task
def generate_excel_task(taxi_id, date, file_identifier, to_emails):
    try:        
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        trajectories = Trajectory.objects.filter(taxi_id=taxi_id, date__date=date_obj)

        wb = Workbook()
        ws = wb.active

        ws.append(['Latitude', 'Longitude'])

        for trajectory in trajectories:
            ws.append([trajectory.latitude, trajectory.longitude])

        excel_content = BytesIO()
        wb.save(excel_content)

        excel_content_file = ContentFile(excel_content.getvalue())

        logger = logging.getLogger(__name__)
        logger.debug(f"excel_content_file: {excel_content_file}")

        directory = '/home/lour/python-projects/fleet_management/generated_files/'

        if not os.path.exists(directory):
            os.makedirs(directory)

        file_path = os.path.join(directory, f'{file_identifier}_trajectories.xlsx')

        with open(file_path, 'wb') as f:
            f.write(excel_content_file.read())

        send_email_task.delay(file_identifier, to_emails)
    except Exception as e:
        logger.error(f"Error generating Excel file: {str(e)}")


@shared_task
def send_email_task(file_identifier, to_emails):
    subject = 'Your file is ready.'

    message = 'You can download your file using the link below:\n\n'
    
    download_link = f'http://127.0.0.1:8000/download_excel?file_identifier={file_identifier}'

    message += download_link

    to_emails_list = [email.strip() for email in to_emails.split(',')]

    smtp_client = Smtp()
    smtp_client.send_email(subject, message, to_emails_list)