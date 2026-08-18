const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const source = path.join(root, 'flacon_server.py');
const resources = path.join(root, 'resources');
const pylance = path.join(resources, 'pylance');

fs.mkdirSync(resources, { recursive: true });
fs.mkdirSync(pylance, { recursive: true });

const content = fs.readFileSync(source, 'utf8');

fs.writeFileSync(path.join(resources, 'flacon_server.py'), content);
fs.writeFileSync(path.join(pylance, 'flacon.py'), content);

console.log('Synced flacon_server.py to extension resources.');
