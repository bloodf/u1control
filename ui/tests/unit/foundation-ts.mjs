// Node strips TypeScript types from the tests' own files but refuses files under node_modules, and the shared
// foundation (@orca-plugins/ui-foundation) ships TypeScript sources. Strip those too: `node --import` this file.
import { readFileSync } from 'node:fs';
import { registerHooks, stripTypeScriptTypes } from 'node:module';
import { fileURLToPath } from 'node:url';

registerHooks({
  load(url, context, nextLoad) {
    if (!url.includes('/node_modules/@orca-plugins/ui-foundation/') || !url.endsWith('.ts')) return nextLoad(url, context);
    return { format: 'module', source: stripTypeScriptTypes(readFileSync(fileURLToPath(url), 'utf8')), shortCircuit: true };
  },
});
