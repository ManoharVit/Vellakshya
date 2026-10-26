/**
 * Netlify Build Script for Vellakshya PDF Workstation
 * Generates dynamic Edge Reverse Proxy rules and preflights static assets.
 * Architect & Lead Developer: Giri Manohar Vemula
 * LinkedIn: https://www.linkedin.com/in/manoharv511
 * GitHub: https://github.com/ManoharVit
 */
const fs = require('fs');
const path = require('path');

// Priority: BACKEND_URL env var -> Render deployment backend target
const targetBackend = process.env.BACKEND_URL || 'https://vellakshya.onrender.com';
const staticDir = path.join(__dirname, 'app', 'static');
const redirectsFile = path.join(staticDir, '_redirects');

console.log(`[Netlify Build] Configuring Edge Reverse Proxy target: ${targetBackend}`);

const redirectsContent = `# Dynamic Netlify Edge Reverse Proxy Rules
/api/*  ${targetBackend}/api/:splat  200!
/*      /index.html                   200
`;

fs.writeFileSync(redirectsFile, redirectsContent, 'utf-8');
console.log(`[Netlify Build] Successfully wrote _redirects to ${redirectsFile}`);
