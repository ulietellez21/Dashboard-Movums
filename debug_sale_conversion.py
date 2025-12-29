
import os
import django
import json
import uuid
import sys
from decimal import Decimal

# Setup Django environment
sys.path.append('/Users/ulisestellez/Documents/agencia-web-project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agencia_web.settings')
django.setup()

from ventas.models import Cotizacion
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from ventas.views import CotizacionConvertirView

def test_conversion():
    print("--- Testing Cotizacion Conversion Logic ---")
    
    # 1. Create a dummy Cotizacion with 2 Flight Proposals
    try:
        # Check for existing logic or create new
        # Need a client
        from crm.models import Cliente
        cliente = Cliente.objects.first()
        if not cliente:
            print("No Client found.")
            return

        cot = Cotizacion(
            cliente=cliente,
            titulo="Debug Cotizacion",
            propuestas={
                'tipo': 'vuelos',
                'vuelos': [
                    {'aerolinea': 'Aero1', 'total': '10,000.00'}, # Index 0
                    {'aerolinea': 'Aero2', 'total': '25,000.00'}  # Index 1
                ]
            }
        )
        cot.save() # Save to get ID/slug
        print(f"Created Cotizacion {cot.slug} with 2 options.")
        
        # 2. Simulate POST to CotizacionConvertirView with index=1
        factory = RequestFactory()
        url = f'/ventas/cotizaciones/{cot.slug}/convertir/'
        request = factory.post(url, {'opcion_vuelo_index': '1'}) # Selecting Option 2
        request.user = django.contrib.auth.models.User.objects.first()
        
        # Add session support
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()
        
        # Run View Logic
        view = CotizacionConvertirView()
        # View uses kwargs based slug
        # We can call post directly
        response = view.post(request, slug=cot.slug)
        
        print(f"Response code: {response.status_code}")
        if response.status_code == 302:
            print(f"Redirect URL: {response.url}")
        
        # 3. Check Session
        session_data = request.session.get('cotizacion_convertir')
        if session_data:
            print("Session Data Found:")
            print(json.dumps(session_data, indent=2, default=str))
            
            total_saved = session_data.get('total_cotizacion')
            print(f"Total Saved: {total_saved}")
            
            if Decimal(total_saved) == Decimal('25000.00'):
                print("SUCCESS: Logic correctly picked option 1 (25,000).")
            elif Decimal(total_saved) == Decimal('10000.00'):
                print("FAILURE: Logic picked option 0 (10,000) despite input 1.")
            else:
                print(f"FAILURE: Logic picked unknown amount {total_saved}.")
        else:
            print("FAILURE: No session data found.")
            
        # Cleanup
        cot.delete()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_conversion()
