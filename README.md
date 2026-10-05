# Railway deploy
1. GitHub e push -> Railway: New Project -> Deploy from repo
2. Variables: SECRET_KEY (random), ADMIN_USER, ADMIN_PASS, SITE_NAME (optional), GOOGLE_CLIENT_ID (Google login er jonno)
3. Volume add korun, mount /data, Variable: DB_PATH=/data/data.db  (na dile redeploy e data harabe)
4. Settings -> Networking -> Generate Domain
5. Admin login -> Profile -> Admin Panel. Payment number, Telegram link, popup text Admin > Settings theke change korun.
