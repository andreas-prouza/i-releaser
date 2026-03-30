## Apache config

Important: 
* Use `ProxyPass` and `ProxyPassReverse`
* Add `ProxyPreserveHost On`!


```apache
<VirtualHost *:8080>

  ProxyPreserveHost On
  ProxyPass http://127.0.0.1:8002/
  ProxyPassReverse http://127.0.0.1:8002/

</VirtualHost>
```