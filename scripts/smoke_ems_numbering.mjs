// scripts/smoke_ems_numbering.mjs — verify the EMS front-matter + family numbering.
// Zero new deps: transpiles the TS module with esbuild (already installed via Vite).
import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, resolve } from 'node:path';
import { createRequire } from 'node:module';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const src = resolve(root, 'frontend/src/model/emsNumbering.ts');

// Load esbuild from the frontend's node_modules (already installed via Vite).
const require = createRequire(pathToFileURL(resolve(root, 'frontend/package.json')));
const { build } = require('esbuild');

// Bundle the module (its only import is a type-only import of ./types, dropped at compile).
const out = await build({
  entryPoints: [src],
  bundle: true,
  format: 'esm',
  write: false,
  logLevel: 'silent',
  external: ['./types'],
});
const code = out.outputFiles[0].text.replace(/from\s*["']\.\/types["'];?/g, ';');
const mod = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const { classifyPageFamily, generateEmsCodes } = mod;

const problems = [];
const page = (id, sheetTitle, extra = {}) => ({ id, sheetTitle, sheetTab: '', include: true, ...extra });

// Front matter → fixed 0.x sub-index.
const fm = [
  ['Cover Sheet / Project Info', 'EMS 0.0'],
  ['Sheet Index', 'EMS 0.1'],
  ['Project Directory', 'EMS 0.2'],
  ['General Notes & Guidelines', 'EMS 0.3'],
  ['Project Scope', 'EMS 0.4'],
  ['Responsibility Matrix', 'EMS 0.5'],
  ['Bill of Materials', 'EMS 0.6'],
  ['Revision Log', 'EMS 0.7'],
];
const fmPages = fm.map(([t], i) => page(`f${i}`, t));
const fmCodes = generateEmsCodes(fmPages);
for (let i = 0; i < fm.length; i += 1) {
  const got = fmCodes.get(`f${i}`);
  if (got !== fm[i][1]) problems.push(`front matter "${fm[i][0]}" → ${got} (expected ${fm[i][1]})`);
}

// Technical families numbered within family.
const tech = [
  page('t1', 'IDF Rack A Layout'),        // family 2
  page('t2', 'BACnet Riser'),             // family 2
  page('t3', 'DLE Case Control'),         // family 3
  page('t4', 'LCP Lighting Output Matrix'), // family 5
  page('t5', 'LCP Wiring Schematic'),     // family 8 (schematic wins)
];
const techCodes = generateEmsCodes(tech);
const expectTech = { t1: 'EMS 2.1', t2: 'EMS 2.2', t3: 'EMS 3.1', t4: 'EMS 5.1', t5: 'EMS 8.1' };
for (const [id, want] of Object.entries(expectTech)) {
  const got = techCodes.get(id);
  if (got !== want) problems.push(`tech ${id} → ${got} (expected ${want})`);
}

// Continuation inherits base code + letter suffix.
const withCont = [
  page('b1', 'IDF Rack A Layout'),
  page('c1', 'IDF Rack A Layout — CONTINUED', { continuationOf: 'b1', continuationIndex: 1 }),
];
const contCodes = generateEmsCodes(withCont);
if (contCodes.get('c1') !== `${contCodes.get('b1')}a`) {
  problems.push(`continuation → ${contCodes.get('c1')} (expected ${contCodes.get('b1')}a)`);
}

// Custom prefix (RDM).
const rdm = generateEmsCodes([page('r1', 'Cover Sheet')], 'RDM');
if (rdm.get('r1') !== 'RDM 0.0') problems.push(`custom prefix → ${rdm.get('r1')} (expected RDM 0.0)`);

// Classifier labels are sane.
if (classifyPageFamily(page('x', 'BACnet Riser')).kind !== 'family') {
  problems.push('BACnet not classified as a family page');
}

if (problems.length) {
  console.log('EMS NUMBERING PROBLEMS:');
  for (const p of problems) console.log(`  - ${p}`);
  process.exit(1);
}
console.log('OK: EMS numbering checks passed.');
