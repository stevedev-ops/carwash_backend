import os
from pathlib import Path
from django.shortcuts import render
from django.views.generic import View
from django.http import HttpResponse

BASE_DIR = Path(__file__).resolve().parent.parent

class SinglePageAppView(View):
    """
    Renders the Single Page Application index.html.
    All client-side routes will load this view.
    """
    def get(self, request, *args, **kwargs):
        return render(request, 'index.html')

class ServiceWorkerView(View):
    """
    Serves the root service-worker.js for full-scope offline caching.
    """
    def get(self, request, *args, **kwargs):
        sw_path = BASE_DIR / 'static' / 'sw.js'
        if sw_path.exists():
            with open(sw_path, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = "// Service worker placeholder"
        response = HttpResponse(content, content_type='application/javascript')
        response['Service-Worker-Allowed'] = '/'
        return response

class ManifestView(View):
    """
    Serves the PWA Web App Manifest.
    """
    def get(self, request, *args, **kwargs):
        manifest_path = BASE_DIR / 'static' / 'manifest.json'
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = "{}"
        return HttpResponse(content, content_type='application/manifest+json')

