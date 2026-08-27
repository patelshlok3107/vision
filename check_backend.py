import os, django, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ai.services.router import classify_intent, resolve_model
print('router imports OK')
r1 = classify_intent('Hello', False, 'auto')
print('Hello:', r1['mode'], 'simple=', r1['is_simple'])
r2 = classify_intent('What is HTML?', False, 'auto')
print('HTML?:', r2['mode'], 'simple=', r2['is_simple'])
r3 = classify_intent('Write a react e-commerce website', False, 'auto')
print('code:', r3['mode'], 'simple=', r3['is_simple'])

from ai.services.agent import VisionAgent
print('Agent import OK')
from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.filter(email='test@vision.ai').first()
agent = VisionAgent(user=u)
print('Agent instantiated OK')
fn = getattr(agent, '_build_ultrafast_messages', None)
print('_build_ultrafast_messages exists: ', fn is not None)
msgs = agent._build_ultrafast_messages(None, 'Hello', [])
print('_build returns count=', len(msgs))
print('All backend checks OK')
