import os

def export_envs(request):
    return {
        'ENV': os.environ
    }
