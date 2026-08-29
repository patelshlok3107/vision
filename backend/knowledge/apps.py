from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'knowledge'

    def ready(self):
        # Ensure admin user exists with email admin123@gmail.com for live server convenience
        try:
            from django.contrib.auth import get_user_model
            from django.conf import settings
            from decouple import config as decouple_config
            User = get_user_model()
            # Only run if DB is ready and not during migrations
            import sys
            if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
                return
            admin_email = getattr(settings, 'ADMIN_EMAIL', None) or decouple_config('ADMIN_EMAIL', default='admin123@gmail.com')
            admin_pass = getattr(settings, 'ADMIN_PASSWORD', None) or decouple_config('ADMIN_PASSWORD', default='admin123')
            if admin_email and admin_pass:
                if not User.objects.filter(email__iexact=admin_email).exists():
                    try:
                        # username must be unique, use email local part or admin123
                        username = admin_email.split('@')[0] or 'admin123'
                        # Ensure username unique
                        base = username
                        counter = 1
                        while User.objects.filter(username=username).exists():
                            username = f"{base}{counter}"
                            counter += 1
                        user = User.objects.create_user(username=username, email=admin_email.lower(), password=admin_pass)
                        user.is_staff = True
                        user.is_superuser = True
                        user.save(update_fields=['is_staff', 'is_superuser'])
                    except Exception:
                        pass
                else:
                    # Ensure existing admin is staff/superuser and password is correct
                    try:
                        u = User.objects.filter(email__iexact=admin_email).first()
                        if u:
                            needs_save = False
                            if not u.is_staff:
                                u.is_staff = True
                                needs_save = True
                            if not u.is_superuser:
                                u.is_superuser = True
                                needs_save = True
                            if needs_save:
                                u.save(update_fields=['is_staff', 'is_superuser'])
                            # Optionally reset password to env value if check fails (dev convenience)
                            try:
                                if not u.check_password(admin_pass):
                                    u.set_password(admin_pass)
                                    u.save(update_fields=['password'])
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass
