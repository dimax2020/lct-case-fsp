import { loadConfig } from '@epa/platform';
import { buildPlatform } from './container.js';

/** Bootstraps an organisation with an employer, an auditor and a platform operator token. */
const config = loadConfig();
const platform = await buildPlatform({ config });
const orgName = process.argv[2] ?? 'Demo Org';
const orgId = await platform.auth.createOrganisation(orgName);
const employer = await platform.auth.createStaff(orgId, process.argv[3] ?? 'employer@demo.local', 'employer');
const auditor = await platform.auth.createStaff(orgId, 'auditor@demo.local', 'auditor');
const platformToken = await platform.auth.platformToken();
process.stdout.write(
  JSON.stringify({ organisationId: orgId, employerToken: employer.token, auditorToken: auditor.token, platformToken }, null, 2) + '\n',
);
await platform.close();
