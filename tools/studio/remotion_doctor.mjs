import {createHash, randomBytes} from 'node:crypto';
import {createReadStream} from 'node:fs';
import {
  lstat,
  open,
  readFile,
  readdir,
  realpath,
  rename,
  rm,
  stat,
} from 'node:fs/promises';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const PINNED_REMOTION_VERSION = '4.0.517';
const ATTESTATION_SCHEMA_VERSION = 1;
const ATTESTATION_ALGORITHM = 'sha256-node-dependency-closure-v1';
const ATTESTATION_FILENAME = '.minimaxh3-remotion-runtime-attestation.json';
const MAX_PACKAGE_JSON_BYTES = 1024 * 1024;
const MAX_ATTESTATION_BYTES = 64 * 1024;
const MAX_CLOSURE_PACKAGES = 10_000;
const MAX_CLOSURE_FILES = 1_000_000;
const MAX_CLOSURE_BYTES = 16 * 1024 * 1024 * 1024;
const HASH_CONCURRENCY = 16;
const PACKAGE_NAME_RE = /^(?:@[a-z0-9][a-z0-9._-]*\/[a-z0-9][a-z0-9._-]*|[a-z0-9][a-z0-9._-]*)$/iu;
const HEX_SHA256_RE = /^[0-9A-F]{64}$/u;

export const REMOTION_PACKAGE_NAMES = Object.freeze([
  'remotion',
  '@remotion/player',
  '@remotion/renderer',
  '@remotion/bundler',
  '@remotion/transitions',
]);
export const RUNTIME_ROOT_PACKAGE_NAMES = Object.freeze([
  ...REMOTION_PACKAGE_NAMES,
  'playwright',
]);
export const RUNTIME_ATTESTATION_ALGORITHM = ATTESTATION_ALGORITHM;
export const RUNTIME_ATTESTATION_FILENAME = ATTESTATION_FILENAME;

const defaultStudioRoot = fileURLToPath(new URL('../../studio/', import.meta.url));

class RuntimeAttestationError extends Error {
  constructor(message) {
    super(message);
    this.name = 'RuntimeAttestationError';
  }
}

const fail = (message) => {
  throw new RuntimeAttestationError(message);
};

const isWithin = (root, candidate) => {
  const relative = path.relative(root, candidate);
  return relative === '' || (!path.isAbsolute(relative) && relative !== '..' && !relative.startsWith(`..${path.sep}`));
};

const portableRelative = (root, candidate) => {
  const relative = path.relative(root, candidate);
  if (!relative || path.isAbsolute(relative) || relative === '..' || relative.startsWith(`..${path.sep}`)) {
    fail('Runtime dependency closure escaped its installation root');
  }
  return relative.split(path.sep).join('/');
};

const packagePathParts = (name) => {
  if (typeof name !== 'string' || !PACKAGE_NAME_RE.test(name)) {
    fail('Runtime dependency closure contains an invalid package name');
  }
  return name.split('/');
};

const pathKey = (value) => process.platform === 'win32' ? value.toLocaleLowerCase('en-US') : value;

const safeLstat = async (candidate, message) => {
  try {
    return await lstat(candidate, {bigint: true});
  } catch {
    fail(message);
  }
};

const assertPlainDirectory = async (candidate, containmentRoot, message) => {
  const lexical = path.resolve(candidate);
  if (!isWithin(containmentRoot, lexical)) {
    fail('Runtime dependency closure escaped its installation root');
  }
  const metadata = await safeLstat(lexical, message);
  if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
    fail(message);
  }
  let resolved;
  try {
    resolved = await realpath(lexical);
  } catch {
    fail(message);
  }
  if (!isWithin(containmentRoot, resolved) || pathKey(resolved) !== pathKey(lexical)) {
    fail('Runtime dependency closure contains an unsafe directory');
  }
  return resolved;
};

const readPackageJson = async (packageDirectory, expectedName) => {
  const packageJsonPath = path.join(packageDirectory, 'package.json');
  const metadata = await safeLstat(packageJsonPath, 'Runtime dependency package metadata is unavailable');
  if (
    metadata.isSymbolicLink()
    || !metadata.isFile()
    || metadata.size < 2n
    || metadata.size > BigInt(MAX_PACKAGE_JSON_BYTES)
  ) {
    fail('Runtime dependency package metadata is unsafe');
  }
  let parsed;
  try {
    parsed = JSON.parse(await readFile(packageJsonPath, 'utf8'));
  } catch {
    fail('Runtime dependency package metadata is invalid');
  }
  if (
    parsed === null
    || typeof parsed !== 'object'
    || Array.isArray(parsed)
    || parsed.name !== expectedName
    || typeof parsed.version !== 'string'
    || parsed.version.length < 1
    || parsed.version.length > 256
  ) {
    fail('Runtime dependency package identity is invalid');
  }
  return parsed;
};

const dependencyNames = (packageJson) => {
  const required = new Set();
  const optional = new Set();
  const addSection = (section, destination) => {
    if (section === undefined) {
      return;
    }
    if (section === null || typeof section !== 'object' || Array.isArray(section)) {
      fail('Runtime dependency package metadata is invalid');
    }
    for (const name of Object.keys(section)) {
      packagePathParts(name);
      destination.add(name);
    }
  };
  addSection(packageJson.dependencies, required);
  addSection(packageJson.optionalDependencies, optional);
  for (const name of optional) {
    required.delete(name);
  }
  if (packageJson.peerDependencies !== undefined) {
    if (
      packageJson.peerDependencies === null
      || typeof packageJson.peerDependencies !== 'object'
      || Array.isArray(packageJson.peerDependencies)
    ) {
      fail('Runtime dependency package metadata is invalid');
    }
    const peerMeta = packageJson.peerDependenciesMeta;
    if (peerMeta !== undefined && (peerMeta === null || typeof peerMeta !== 'object' || Array.isArray(peerMeta))) {
      fail('Runtime dependency package metadata is invalid');
    }
    for (const name of Object.keys(packageJson.peerDependencies)) {
      packagePathParts(name);
      const metadata = peerMeta?.[name];
      if (metadata !== undefined && (metadata === null || typeof metadata !== 'object' || Array.isArray(metadata))) {
        fail('Runtime dependency package metadata is invalid');
      }
      if (metadata?.optional === true) {
        optional.add(name);
        required.delete(name);
      } else if (!optional.has(name)) {
        required.add(name);
      }
    }
  }
  return {
    required: [...required].sort(),
    optional: [...optional].filter((name) => !required.has(name)).sort(),
  };
};

const dependencyCandidate = async (candidate, modulesRoot) => {
  let metadata;
  try {
    metadata = await lstat(candidate, {bigint: true});
  } catch (error) {
    if (error?.code === 'ENOENT' || error?.code === 'ENOTDIR') {
      return null;
    }
    fail('Runtime dependency closure cannot be inspected');
  }
  if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
    fail('Runtime dependency closure contains an unsafe package directory');
  }
  return assertPlainDirectory(
    candidate,
    modulesRoot,
    'Runtime dependency closure contains an unsafe package directory',
  );
};

const resolveDependencyDirectory = async ({fromDirectory, name, studioRoot, modulesRoot}) => {
  const parts = packagePathParts(name);
  let current = fromDirectory;
  while (isWithin(studioRoot, current)) {
    const resolved = await dependencyCandidate(path.join(current, 'node_modules', ...parts), modulesRoot);
    if (resolved !== null) {
      return resolved;
    }
    if (pathKey(current) === pathKey(studioRoot)) {
      break;
    }
    current = path.dirname(current);
  }
  return null;
};

const hashPlainFile = async (filePath) => {
  const before = await safeLstat(filePath, 'Runtime dependency file is unavailable');
  if (before.isSymbolicLink() || !before.isFile() || before.size < 0n || before.size > BigInt(Number.MAX_SAFE_INTEGER)) {
    fail('Runtime dependency closure contains an unsafe file');
  }
  const digest = createHash('sha256');
  try {
    for await (const chunk of createReadStream(filePath)) {
      digest.update(chunk);
    }
  } catch {
    fail('Runtime dependency file cannot be read');
  }
  const after = await safeLstat(filePath, 'Runtime dependency file is unavailable');
  if (
    after.isSymbolicLink()
    || !after.isFile()
    || before.dev !== after.dev
    || before.ino !== after.ino
    || before.size !== after.size
    || before.mtimeNs !== after.mtimeNs
  ) {
    fail('Runtime dependency closure changed while it was inspected');
  }
  return {bytes: Number(before.size), sha256: digest.digest('hex').toUpperCase()};
};

const collectPackageFiles = async (packageDirectory) => {
  const pendingFiles = [];
  const visit = async (directory, relativeDirectory = '') => {
    let entries;
    try {
      entries = await readdir(directory, {withFileTypes: true});
    } catch {
      fail('Runtime dependency directory cannot be read');
    }
    entries.sort((left, right) => left.name.localeCompare(right.name, 'en'));
    for (const entry of entries) {
      const candidate = path.join(directory, entry.name);
      const relativePath = relativeDirectory ? `${relativeDirectory}/${entry.name}` : entry.name;
      if (entry.isSymbolicLink()) {
        fail('Runtime dependency closure contains a symbolic link');
      }
      if (entry.name === 'node_modules') {
        if (!entry.isDirectory()) {
          fail('Runtime dependency closure contains an unsafe node_modules entry');
        }
        continue;
      }
      if (entry.isDirectory()) {
        const metadata = await safeLstat(candidate, 'Runtime dependency entry is unavailable');
        if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
          fail('Runtime dependency closure contains an unsafe directory');
        }
        await visit(candidate, relativePath);
        continue;
      }
      if (!entry.isFile()) {
        fail('Runtime dependency closure contains a special file');
      }
      pendingFiles.push({path: relativePath, filePath: candidate});
      if (pendingFiles.length > MAX_CLOSURE_FILES) {
        fail('Runtime dependency closure contains too many files');
      }
    }
  };
  await visit(packageDirectory);
  pendingFiles.sort((left, right) => left.path.localeCompare(right.path, 'en'));
  const files = new Array(pendingFiles.length);
  let nextIndex = 0;
  const worker = async () => {
    while (nextIndex < pendingFiles.length) {
      const index = nextIndex;
      nextIndex += 1;
      const pending = pendingFiles[index];
      files[index] = {path: pending.path, ...await hashPlainFile(pending.filePath)};
    }
  };
  await Promise.all(
    Array.from({length: Math.min(HASH_CONCURRENCY, pendingFiles.length)}, () => worker()),
  );
  return files;
};

const resolveRoots = async (requestedStudioRoot) => {
  const lexicalStudioRoot = path.resolve(requestedStudioRoot);
  const studioMetadata = await safeLstat(lexicalStudioRoot, 'Studio dependency root is unavailable');
  if (studioMetadata.isSymbolicLink() || !studioMetadata.isDirectory()) {
    fail('Studio dependency root is unsafe');
  }
  let studioRoot;
  try {
    studioRoot = await realpath(lexicalStudioRoot);
  } catch {
    fail('Studio dependency root is unavailable');
  }
  const modulesRoot = await assertPlainDirectory(
    path.join(studioRoot, 'node_modules'),
    studioRoot,
    'Studio node_modules is unavailable or unsafe',
  );
  return {studioRoot, modulesRoot};
};

const validateRootPackageNames = (rootPackageNames) => {
  if (!Array.isArray(rootPackageNames) || rootPackageNames.length < 1) {
    fail('Runtime attestation roots are invalid');
  }
  const roots = rootPackageNames.map((name) => {
    packagePathParts(name);
    return name;
  });
  if (new Set(roots).size !== roots.length) {
    fail('Runtime attestation roots are invalid');
  }
  return [...roots].sort();
};

export const buildRuntimeAttestation = async ({
  studioRoot: requestedStudioRoot = defaultStudioRoot,
  rootPackageNames = RUNTIME_ROOT_PACKAGE_NAMES,
} = {}) => {
  const roots = validateRootPackageNames(rootPackageNames);
  const {studioRoot, modulesRoot} = await resolveRoots(requestedStudioRoot);
  const queue = [];
  for (const name of roots) {
    const directory = await resolveDependencyDirectory({
      fromDirectory: studioRoot,
      name,
      studioRoot,
      modulesRoot,
    });
    if (directory === null) {
      fail(`Required runtime package ${name} is unavailable`);
    }
    queue.push({name, directory});
  }

  const packages = [];
  const visited = new Set();
  while (queue.length > 0) {
    const current = queue.shift();
    const key = pathKey(current.directory);
    if (visited.has(key)) {
      continue;
    }
    visited.add(key);
    if (visited.size > MAX_CLOSURE_PACKAGES) {
      fail('Runtime dependency closure contains too many packages');
    }
    const packageJson = await readPackageJson(current.directory, current.name);
    const logicalPath = portableRelative(modulesRoot, current.directory);
    packages.push({
      name: current.name,
      version: packageJson.version,
      logicalPath,
      files: await collectPackageFiles(current.directory),
    });
    const dependencies = dependencyNames(packageJson);
    for (const name of dependencies.required) {
      const directory = await resolveDependencyDirectory({
        fromDirectory: current.directory,
        name,
        studioRoot,
        modulesRoot,
      });
      if (directory === null) {
        fail(`Required runtime dependency ${name} is unavailable`);
      }
      queue.push({name, directory});
    }
    for (const name of dependencies.optional) {
      const directory = await resolveDependencyDirectory({
        fromDirectory: current.directory,
        name,
        studioRoot,
        modulesRoot,
      });
      if (directory !== null) {
        queue.push({name, directory});
      }
    }
  }

  packages.sort((left, right) => left.logicalPath.localeCompare(right.logicalPath, 'en'));
  const aggregate = createHash('sha256');
  aggregate.update(`${ATTESTATION_ALGORITHM}\0`);
  let fileCount = 0;
  let totalBytes = 0;
  for (const packageEntry of packages) {
    aggregate.update(`P\0${packageEntry.logicalPath}\0${packageEntry.name}\0${packageEntry.version}\0`);
    for (const file of packageEntry.files) {
      aggregate.update(`F\0${file.path}\0${file.bytes}\0${file.sha256}\0`);
      fileCount += 1;
      totalBytes += file.bytes;
      if (!Number.isSafeInteger(totalBytes) || totalBytes > MAX_CLOSURE_BYTES) {
        fail('Runtime dependency closure is too large');
      }
    }
  }
  return {
    schema_version: ATTESTATION_SCHEMA_VERSION,
    algorithm: ATTESTATION_ALGORITHM,
    root_packages: roots,
    closure_package_count: packages.length,
    file_count: fileCount,
    total_bytes: totalBytes,
    tree_sha256: aggregate.digest('hex').toUpperCase(),
  };
};

const assertAttestationShape = (value, expectedRoots) => {
  if (
    value === null
    || typeof value !== 'object'
    || Array.isArray(value)
    || Object.keys(value).sort().join(',') !== [
      'algorithm',
      'closure_package_count',
      'file_count',
      'root_packages',
      'schema_version',
      'total_bytes',
      'tree_sha256',
    ].sort().join(',')
    || value.schema_version !== ATTESTATION_SCHEMA_VERSION
    || value.algorithm !== ATTESTATION_ALGORITHM
    || !Array.isArray(value.root_packages)
    || JSON.stringify(value.root_packages) !== JSON.stringify(expectedRoots)
    || !Number.isSafeInteger(value.closure_package_count)
    || value.closure_package_count < expectedRoots.length
    || value.closure_package_count > MAX_CLOSURE_PACKAGES
    || !Number.isSafeInteger(value.file_count)
    || value.file_count < expectedRoots.length
    || value.file_count > MAX_CLOSURE_FILES
    || !Number.isSafeInteger(value.total_bytes)
    || value.total_bytes < 1
    || typeof value.tree_sha256 !== 'string'
    || !HEX_SHA256_RE.test(value.tree_sha256)
  ) {
    fail('Runtime dependency attestation is invalid');
  }
};

const attestationTarget = async (requestedStudioRoot) => {
  const roots = await resolveRoots(requestedStudioRoot);
  return {...roots, target: path.join(roots.modulesRoot, ATTESTATION_FILENAME)};
};

export const writeRuntimeAttestation = async ({
  studioRoot: requestedStudioRoot = defaultStudioRoot,
  rootPackageNames = RUNTIME_ROOT_PACKAGE_NAMES,
} = {}) => {
  const roots = validateRootPackageNames(rootPackageNames);
  const attestation = await buildRuntimeAttestation({
    studioRoot: requestedStudioRoot,
    rootPackageNames: roots,
  });
  const {modulesRoot, target} = await attestationTarget(requestedStudioRoot);
  let existing;
  try {
    existing = await lstat(target, {bigint: true});
  } catch (error) {
    if (error?.code !== 'ENOENT') {
      fail('Runtime dependency attestation cannot be inspected');
    }
  }
  if (existing && (existing.isSymbolicLink() || !existing.isFile())) {
    fail('Runtime dependency attestation target is unsafe');
  }
  if (!isWithin(modulesRoot, target)) {
    fail('Runtime dependency attestation target is unsafe');
  }

  const nonce = `${process.pid}-${randomBytes(12).toString('hex')}`;
  const partial = path.join(modulesRoot, `${ATTESTATION_FILENAME}.${nonce}.partial`);
  const backup = path.join(modulesRoot, `${ATTESTATION_FILENAME}.${nonce}.backup`);
  let handle;
  let movedExisting = false;
  try {
    handle = await open(partial, 'wx', 0o600);
    await handle.writeFile(`${JSON.stringify(attestation)}\n`, 'utf8');
    await handle.sync();
    await handle.close();
    handle = undefined;
    if (existing) {
      await rename(target, backup);
      movedExisting = true;
    }
    await rename(partial, target);
    if (movedExisting) {
      await rm(backup, {force: true});
      movedExisting = false;
    }
  } catch {
    if (handle) {
      await handle.close().catch(() => undefined);
    }
    if (movedExisting) {
      let targetExists = false;
      try {
        await lstat(target);
        targetExists = true;
      } catch {
        targetExists = false;
      }
      if (!targetExists) {
        try {
          await rename(backup, target);
          movedExisting = false;
        } catch {
          // Preserve the backup for manual recovery if restoration fails.
        }
      } else {
        try {
          await rm(backup, {force: true});
          movedExisting = false;
        } catch {
          // Preserve the backup if cleanup fails.
        }
      }
    }
    fail('Runtime dependency attestation could not be written');
  } finally {
    await rm(partial, {force: true}).catch(() => undefined);
    if (!movedExisting) {
      await rm(backup, {force: true}).catch(() => undefined);
    }
  }
  return attestation;
};

export const verifyRuntimeAttestation = async ({
  studioRoot: requestedStudioRoot = defaultStudioRoot,
  rootPackageNames = RUNTIME_ROOT_PACKAGE_NAMES,
} = {}) => {
  const roots = validateRootPackageNames(rootPackageNames);
  const {target} = await attestationTarget(requestedStudioRoot);
  const metadata = await safeLstat(target, 'Runtime dependency attestation is unavailable. Run setup-studio.ps1.');
  if (
    metadata.isSymbolicLink()
    || !metadata.isFile()
    || metadata.size < 2n
    || metadata.size > BigInt(MAX_ATTESTATION_BYTES)
  ) {
    fail('Runtime dependency attestation is unsafe');
  }
  let recorded;
  try {
    recorded = JSON.parse(await readFile(target, 'utf8'));
  } catch {
    fail('Runtime dependency attestation is invalid');
  }
  assertAttestationShape(recorded, roots);
  const current = await buildRuntimeAttestation({
    studioRoot: requestedStudioRoot,
    rootPackageNames: roots,
  });
  if (JSON.stringify(recorded) !== JSON.stringify(current)) {
    fail('Runtime dependency attestation does not match installed files. Run setup-studio.ps1.');
  }
  return current;
};

const verifyPinnedRuntime = async (studioRoot) => {
  const runtimeAttestation = await verifyRuntimeAttestation({studioRoot});
  const requireFromStudio = createRequire(path.join(studioRoot, 'package.json'));
  const packages = {};
  for (const name of REMOTION_PACKAGE_NAMES) {
    const packageJson = requireFromStudio(`${name}/package.json`);
    if (packageJson.version !== PINNED_REMOTION_VERSION) {
      fail(`${name} must be pinned to ${PINNED_REMOTION_VERSION}`);
    }
    packages[name] = packageJson.version;
  }

  const playwrightPackage = requireFromStudio('playwright/package.json');
  const {chromium} = requireFromStudio('playwright');
  const chromiumExecutablePath = chromium.executablePath();
  let executableStat;
  try {
    executableStat = await stat(chromiumExecutablePath);
  } catch {
    fail('Pinned Playwright Chromium is unavailable');
  }
  if (!executableStat.isFile()) {
    fail('Pinned Playwright Chromium is unavailable');
  }

  let browser;
  try {
    browser = await chromium.launch({
      executablePath: chromiumExecutablePath,
      headless: true,
      args: ['--disable-background-networking'],
    });
  } catch {
    fail('Pinned Playwright Chromium could not be launched');
  }
  let chromiumVersion;
  try {
    chromiumVersion = browser.version();
  } finally {
    await browser.close().catch(() => undefined);
  }
  return {
    schema_version: 1,
    remotion_packages: packages,
    playwright_version: playwrightPackage.version,
    chromium_executable_path: chromiumExecutablePath,
    chromium_version: chromiumVersion,
    runtime_attestation: runtimeAttestation,
  };
};

const main = async () => {
  const argumentsList = process.argv.slice(2);
  if (argumentsList.length > 1) {
    fail('Unsupported Remotion doctor arguments');
  }
  let result;
  if (argumentsList[0] === '--write-attestation') {
    result = {
      schema_version: 1,
      runtime_attestation: await writeRuntimeAttestation(),
    };
  } else if (argumentsList[0] === '--verify-attestation-only') {
    result = {
      schema_version: 1,
      runtime_attestation: await verifyRuntimeAttestation(),
    };
  } else if (argumentsList.length === 0) {
    result = await verifyPinnedRuntime(defaultStudioRoot);
  } else {
    fail('Unsupported Remotion doctor arguments');
  }
  process.stdout.write(`${JSON.stringify(result)}\n`);
};

const isMainModule = Boolean(process.argv[1])
  && pathKey(path.resolve(process.argv[1])) === pathKey(path.resolve(fileURLToPath(import.meta.url)));
if (isMainModule) {
  try {
    await main();
  } catch (error) {
    const message = error instanceof RuntimeAttestationError
      ? error.message
      : 'Remotion runtime verification failed';
    process.stderr.write(`${message}\n`);
    process.exitCode = 1;
  }
}
