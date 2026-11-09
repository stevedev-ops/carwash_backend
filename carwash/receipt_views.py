import io
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework import permissions, status
from .models import CarWash
from reportlab.lib.pagesizes import A6
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

class CarWashCustomerReceiptView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk=None):
        car_wash = CarWash.objects.filter(id=pk).select_related('vehicle', 'logged_by').prefetch_related('services').first()
        if not car_wash:
            return HttpResponse("Car wash transaction not found", status=status.HTTP_404_NOT_FOUND)

        buffer = io.BytesIO()
        # Thermal receipt size (A6 format)
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=A6, 
            rightMargin=18, 
            leftMargin=18, 
            topMargin=18, 
            bottomMargin=18
        )
        elements = []
        styles = getSampleStyleSheet()

        brand_style = ParagraphStyle(
            'ReceiptBrand',
            parent=styles['Heading1'],
            fontSize=14,
            alignment=1, # Center
            textColor=colors.HexColor('#0F172A'),
            spaceAfter=2
        )
        center_sub = ParagraphStyle(
            'ReceiptSub',
            parent=styles['Normal'],
            fontSize=7,
            alignment=1, # Center
            textColor=colors.HexColor('#64748B'),
            spaceAfter=6
        )
        normal_style = ParagraphStyle(
            'ReceiptNormal',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#1E293B')
        )
        bold_style = ParagraphStyle(
            'ReceiptBold',
            parent=styles['Normal'],
            fontSize=8,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#0F172A')
        )

        elements.append(Paragraph("SHELL CAR WASH & DETAILING", brand_style))
        elements.append(Paragraph("Nairobi Station • Tel: +254 700 000 000<br/>Official Payment Receipt", center_sub))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#CBD5E1'), spaceAfter=8))

        # Receipt Meta
        meta_data = [
            [Paragraph("Receipt No:", normal_style), Paragraph(f"#{car_wash.id:05d}", bold_style)],
            [Paragraph("Date & Time:", normal_style), Paragraph(car_wash.created_at.strftime('%d/%m/%Y %H:%M'), normal_style)],
            [Paragraph("Vehicle Plate:", normal_style), Paragraph(car_wash.vehicle.plate_number, bold_style)],
            [Paragraph("Vehicle Model:", normal_style), Paragraph(car_wash.vehicle.make_model or car_wash.vehicle.get_vehicle_type_display(), normal_style)],
            [Paragraph("Bay Station:", normal_style), Paragraph(f"Bay {car_wash.bay_number or 1}", normal_style)],
            [Paragraph("Payment:", normal_style), Paragraph(f"{car_wash.get_payment_method_display()} ({car_wash.payment_reference or 'Cash'})", normal_style)],
        ]
        t_meta = Table(meta_data, colWidths=[80, 160])
        t_meta.setStyle(TableStyle([
            ('TOPPADDING', (0,0), (-1,-1), 1),
            ('BOTTOMPADDING', (0,0), (-1,-1), 1),
        ]))
        elements.append(t_meta)
        elements.append(Spacer(1, 6))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0'), spaceAfter=6))

        # Services Items
        srv_data = [[Paragraph("<b>Service</b>", normal_style), Paragraph("<b>Price (KSh)</b>", ParagraphStyle('R', parent=normal_style, alignment=2))]]
        for s in car_wash.services.all():
            srv_data.append([
                Paragraph(s.service_name_snapshot, normal_style),
                Paragraph(f"{s.price_charged:,.2f}", ParagraphStyle('R', parent=normal_style, alignment=2))
            ])
        srv_data.append([
            Paragraph("<b>TOTAL PAID</b>", bold_style),
            Paragraph(f"<b>KSh {car_wash.total_amount:,.2f}</b>", ParagraphStyle('R', parent=bold_style, alignment=2))
        ])

        t_srv = Table(srv_data, colWidths=[160, 80])
        t_srv.setStyle(TableStyle([
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#0F172A')),
        ]))
        elements.append(t_srv)

        elements.append(Spacer(1, 10))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#CBD5E1'), spaceAfter=6))
        elements.append(Paragraph("Thank you for choosing Shell Car Wash!<br/>Drive clean and safe.", center_sub))

        doc.build(elements)
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="receipt_{car_wash.vehicle.plate_number}_{car_wash.id}.pdf"'
        return response

