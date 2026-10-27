/**
 * Netlify Build Script for Vellakshya PDF Workstation
 * Generates dynamic Edge Reverse Proxy rules and preflights static assets.
 * Architect & Lead Developer: Giri Manohar Vemula
 * LinkedIn: https://www.linkedin.com/in/manoharv511
 * GitHub: https://github.com/ManoharVit
 */
const fs = require('fs');
const path = require('path');

// Target backend service for Netlify Edge API proxy (if configured)
const targetBackend = process.env.BACKEND_URL;
const staticDir = path.join(__dirname, 'app', 'static');
const redirectsFile = path.join(staticDir, '_redirects');

let redirectsContent = '# Netlify Edge Routing Rules\n';

if (targetBackend) {
  console.log(`[Netlify Build] Configuring Edge Reverse Proxy target: ${targetBackend}`);
  redirectsContent += `/api/*  ${targetBackend}/api/:splat  200!\n`;
} else {
  console.log('[Netlify Build] Zero-backend edge mode active: in-browser pdf-lib engine enabled');
}

redirectsContent += '/*      /index.html                   200\n';

fs.writeFileSync(redirectsFile, redirectsContent, 'utf-8');
console.log(`[Netlify Build] Successfully wrote _redirects to ${redirectsFile}`);
