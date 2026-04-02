# Online Deploy Starter - Marathi

ही package starter आहे. Production deploy करताना environment variables, database, static files, आणि backups नीट configure करावे लागतील.

## Basic steps
1. Git repository वर code push करा.
2. Hosting service मध्ये new web service तयार करा.
3. `DJANGO_SETTINGS_MODULE=msedcl_easy_attendance.settings_production` set करा.
4. `.env.example` मधील values production environment मध्ये भरा.
5. PostgreSQL database configure करा.
6. `python manage.py migrate` run करा.
7. `python manage.py createsuperuser` run करा.

## अजून development बाकी
- Full admin/user isolation
- Self signup
- Approval workflow toggle
- Configurable operator logic master
