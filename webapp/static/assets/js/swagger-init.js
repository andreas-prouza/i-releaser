/*
 * Starts Swagger UI on /docs (templates/docs.html). A file instead of the inline script of FastAPI's page,
 * so /docs works with the Content-Security-Policy of the web app (docs/features/web-ui-security-headers.md).
 */
const container = document.getElementById('swagger-ui');

window.ui = SwaggerUIBundle({
    url: container.dataset.openapiUrl,
    dom_id: '#swagger-ui',
    layout: 'BaseLayout',
    deepLinking: true,
    showExtensions: true,
    showCommonExtensions: true,
    presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
});
