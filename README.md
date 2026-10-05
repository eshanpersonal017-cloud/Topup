# Railway deploy
1. GitHub e push -> Railway: New Project -> Deploy from repo
2. Variables: SECRET_KEY (random), ADMIN_USER, ADMIN_PASS, PAY_NUMBER (bKash/Nagad number), SITE_NAME
3. Volume add korun, mount path /data, Variable: DB_PATH=/data/data.db  (na dile redeploy e data harabe)
4. Settings -> Networking -> Generate Domain. Admin login diye "Admin" tab theke deposit/order approve korben.
