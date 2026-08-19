const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const resources = path.join(root, 'resources');
const source = path.join(resources, 'flacon_server.py');
const pylance = path.join(resources, 'pylance');

fs.mkdirSync(pylance, { recursive: true });

const content = fs.readFileSync(source, 'utf8');

fs.writeFileSync(path.join(pylance, 'flacon.py'), content);

console.log('Synced resources/flacon_server.py to Pylance stub.');
