export const ASSET_MANIFEST_SCHEMA_ID =
  'https://ai-town.local/schemas/asset-manifest.v1.schema.json';

export const ASSET_MANIFEST_SCHEMA = {
  $schema: 'https://json-schema.org/draft/2020-12/schema',
  $id: ASSET_MANIFEST_SCHEMA_ID,
  title: 'AI Town Asset Manifest v1',
  type: 'object',
  additionalProperties: false,
  required: ['schema_version', 'assets', 'licenses'],
  properties: {
    schema_version: { const: 'asset-manifest.v1' },
    assets: {
      type: 'array',
      minItems: 1,
      uniqueItems: true,
      items: { $ref: '#/$defs/AssetManifestEntry' },
    },
    licenses: {
      type: 'array',
      minItems: 1,
      uniqueItems: true,
      items: { $ref: '#/$defs/LicenseRecord' },
    },
  },
  $defs: {
    StableCatalogId: {
      type: 'string',
      minLength: 3,
      maxLength: 160,
      pattern: '^[a-z][a-z0-9_]*(?:\\.[a-z][a-z0-9_]*)+$',
    },
    LicenseId: {
      type: 'string',
      minLength: 9,
      maxLength: 160,
      pattern: '^license\\.[a-z][a-z0-9_]*(?:\\.[a-z][a-z0-9_]*)*$',
    },
    RelativePath: {
      type: 'string',
      minLength: 3,
      maxLength: 240,
      pattern:
        '^(?!/)(?!.*(?:^|/)\\.{1,2}(?:/|$))(?!.*//)[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*$',
    },
    Sha256: {
      type: 'string',
      pattern: '^[a-f0-9]{64}$',
    },
    AssetManifestEntry: {
      type: 'object',
      additionalProperties: false,
      required: [
        'asset_id',
        'type',
        'path',
        'sha256',
        'byte_length',
        'load_group',
        'load_policy',
        'license_id',
        'fallback_asset_id',
      ],
      properties: {
        asset_id: { $ref: '#/$defs/StableCatalogId' },
        type: {
          type: 'string',
          enum: ['image', 'atlas', 'audio', 'font', 'json', 'shader'],
        },
        path: { $ref: '#/$defs/RelativePath' },
        sha256: { $ref: '#/$defs/Sha256' },
        byte_length: {
          type: 'integer',
          minimum: 1,
          maximum: 2_147_483_647,
        },
        load_group: { $ref: '#/$defs/StableCatalogId' },
        load_policy: {
          type: 'string',
          enum: ['required', 'optional'],
        },
        license_id: { $ref: '#/$defs/LicenseId' },
        fallback_asset_id: { $ref: '#/$defs/StableCatalogId' },
      },
    },
    LicenseRecord: {
      type: 'object',
      additionalProperties: false,
      required: [
        'license_id',
        'source_uri',
        'author',
        'terms',
        'acquired_at',
        'license_text_path',
        'license_text_sha256',
      ],
      properties: {
        license_id: { $ref: '#/$defs/LicenseId' },
        source_uri: {
          type: 'string',
          format: 'uri',
          pattern: '^(?:https://|project://)',
          maxLength: 2_048,
        },
        author: {
          type: 'string',
          minLength: 1,
          maxLength: 200,
          pattern: '^[^\\u0000-\\u001F\\u007F]+$',
        },
        terms: {
          type: 'string',
          minLength: 3,
          maxLength: 240,
          pattern:
            '^(?:LicenseRef-[A-Za-z0-9.-]+|[A-Za-z0-9][A-Za-z0-9.+() -]*)$',
        },
        acquired_at: { type: 'string', format: 'date-time' },
        license_text_path: { $ref: '#/$defs/RelativePath' },
        license_text_sha256: { $ref: '#/$defs/Sha256' },
      },
    },
  },
} as const;

export const MANIFEST_DIAGNOSTIC_CODES = [
  'RENDER_MANIFEST_PARSE_FAILED',
  'RENDER_MANIFEST_SCHEMA_VERSION_UNSUPPORTED',
  'RENDER_MANIFEST_SCHEMA_INVALID',
  'RENDER_ASSET_PATH_INVALID',
  'RENDER_ASSET_HASH_MISMATCH',
  'RENDER_ASSET_ID_DUPLICATE',
  'RENDER_ASSET_PATH_DUPLICATE',
  'RENDER_LICENSE_ID_DUPLICATE',
  'RENDER_LICENSE_RECORD_MISSING',
  'RENDER_LICENSE_TEXT_PATH_INVALID',
  'RENDER_LICENSE_TEXT_HASH_MISMATCH',
  'RENDER_LICENSE_TERMS_UNAPPROVED',
  'RENDER_FALLBACK_REFERENCE_INVALID',
  'RENDER_FALLBACK_CYCLE',
] as const;

export type ManifestDiagnosticCode =
  (typeof MANIFEST_DIAGNOSTIC_CODES)[number];

export interface ManifestDiagnostic {
  code: ManifestDiagnosticCode;
  pointer: string;
  assetId?: string;
  licenseId?: string;
}

export interface AssetManifestEntry {
  asset_id: string;
  type: 'image' | 'atlas' | 'audio' | 'font' | 'json' | 'shader';
  path: string;
  sha256: string;
  byte_length: number;
  load_group: string;
  load_policy: 'required' | 'optional';
  license_id: string;
  fallback_asset_id: string;
}

export interface LicenseRecord {
  license_id: string;
  source_uri: string;
  author: string;
  terms: string;
  acquired_at: string;
  license_text_path: string;
  license_text_sha256: string;
}

export interface AssetManifest {
  schema_version: 'asset-manifest.v1';
  assets: AssetManifestEntry[];
  licenses: LicenseRecord[];
}

const STABLE_ID = /^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$/;
const LICENSE_ID = /^license\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$/;
const SHA256 = /^[a-f0-9]{64}$/;
const RELATIVE_PATH =
  /^(?!\/)(?!.*(?:^|\/)\.{1,2}(?:\/|$))(?!.*\/\/)[A-Za-z0-9][A-Za-z0-9._-]*(?:\/[A-Za-z0-9][A-Za-z0-9._-]*)*$/;
const SOURCE_URI = /^(?:https:\/\/|project:\/\/)\S+$/;
const LICENSE_TERMS =
  /^(?:LicenseRef-[A-Za-z0-9.-]+|[A-Za-z0-9][A-Za-z0-9.+() -]*)$/;
const ASSET_TYPES = new Set(['image', 'atlas', 'audio', 'font', 'json', 'shader']);
const LOAD_POLICIES = new Set(['required', 'optional']);

function diagnostic(
  pointer: string,
  assetId?: string,
  licenseId?: string,
): ManifestDiagnostic {
  return {
    code: 'RENDER_MANIFEST_SCHEMA_INVALID',
    pointer,
    ...(assetId ? { assetId } : {}),
    ...(licenseId ? { licenseId } : {}),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactKeys(
  value: Record<string, unknown>,
  allowed: readonly string[],
): boolean {
  return Object.keys(value).every(key => allowed.includes(key));
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(',')}]`;
  }
  if (isRecord(value)) {
    return `{${Object.keys(value)
      .sort()
      .map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value) ?? 'undefined';
}

export function validateManifestSchema(
  value: unknown,
): ManifestDiagnostic[] {
  const issues: ManifestDiagnostic[] = [];
  if (!isRecord(value)) {
    return [diagnostic('/')];
  }
  if (
    !hasExactKeys(value, ['schema_version', 'assets', 'licenses']) ||
    value.schema_version !== 'asset-manifest.v1'
  ) {
    issues.push(diagnostic('/'));
  }
  if (!Array.isArray(value.assets) || value.assets.length < 1) {
    issues.push(diagnostic('/assets'));
  } else {
    const seenAssets = new Set<string>();
    value.assets.forEach((candidate, index) => {
      const pointer = `/assets/${index}`;
      const canonical = canonicalJson(candidate);
      if (seenAssets.has(canonical)) {
        issues.push(diagnostic(pointer));
      } else {
        seenAssets.add(canonical);
      }
      if (!isRecord(candidate)) {
        issues.push(diagnostic(pointer));
        return;
      }
      const assetId =
        typeof candidate.asset_id === 'string' ? candidate.asset_id : undefined;
      const allowed = [
        'asset_id',
        'type',
        'path',
        'sha256',
        'byte_length',
        'load_group',
        'load_policy',
        'license_id',
        'fallback_asset_id',
      ];
      if (!hasExactKeys(candidate, allowed)) {
        issues.push(diagnostic(pointer, assetId));
      }
      const checks: Array<[boolean, string]> = [
        [typeof candidate.asset_id === 'string' && candidate.asset_id.length >= 3 && candidate.asset_id.length <= 160 && STABLE_ID.test(candidate.asset_id), 'asset_id'],
        [typeof candidate.type === 'string' && ASSET_TYPES.has(candidate.type), 'type'],
        [typeof candidate.path === 'string' && candidate.path.length >= 3 && candidate.path.length <= 240 && RELATIVE_PATH.test(candidate.path), 'path'],
        [typeof candidate.sha256 === 'string' && SHA256.test(candidate.sha256), 'sha256'],
        [Number.isInteger(candidate.byte_length) && Number(candidate.byte_length) >= 1 && Number(candidate.byte_length) <= 2_147_483_647, 'byte_length'],
        [typeof candidate.load_group === 'string' && candidate.load_group.length >= 3 && candidate.load_group.length <= 160 && STABLE_ID.test(candidate.load_group), 'load_group'],
        [typeof candidate.load_policy === 'string' && LOAD_POLICIES.has(candidate.load_policy), 'load_policy'],
        [typeof candidate.license_id === 'string' && candidate.license_id.length >= 9 && candidate.license_id.length <= 160 && LICENSE_ID.test(candidate.license_id), 'license_id'],
        [typeof candidate.fallback_asset_id === 'string' && candidate.fallback_asset_id.length >= 3 && candidate.fallback_asset_id.length <= 160 && STABLE_ID.test(candidate.fallback_asset_id), 'fallback_asset_id'],
      ];
      for (const [valid, field] of checks) {
        if (!valid) {
          issues.push(diagnostic(`${pointer}/${field}`, assetId));
        }
      }
    });
  }

  if (!Array.isArray(value.licenses) || value.licenses.length < 1) {
    issues.push(diagnostic('/licenses'));
  } else {
    const seenLicenses = new Set<string>();
    value.licenses.forEach((candidate, index) => {
      const pointer = `/licenses/${index}`;
      const canonical = canonicalJson(candidate);
      if (seenLicenses.has(canonical)) {
        issues.push(diagnostic(pointer));
      } else {
        seenLicenses.add(canonical);
      }
      if (!isRecord(candidate)) {
        issues.push(diagnostic(pointer));
        return;
      }
      const licenseId =
        typeof candidate.license_id === 'string'
          ? candidate.license_id
          : undefined;
      const allowed = [
        'license_id',
        'source_uri',
        'author',
        'terms',
        'acquired_at',
        'license_text_path',
        'license_text_sha256',
      ];
      if (!hasExactKeys(candidate, allowed)) {
        issues.push(diagnostic(pointer, undefined, licenseId));
      }
      const acquiredAt =
        typeof candidate.acquired_at === 'string'
          ? candidate.acquired_at
          : '';
      const checks: Array<[boolean, string]> = [
        [typeof candidate.license_id === 'string' && candidate.license_id.length >= 9 && candidate.license_id.length <= 160 && LICENSE_ID.test(candidate.license_id), 'license_id'],
        [typeof candidate.source_uri === 'string' && candidate.source_uri.length <= 2_048 && SOURCE_URI.test(candidate.source_uri), 'source_uri'],
        [typeof candidate.author === 'string' && candidate.author.length >= 1 && candidate.author.length <= 200 && !/[\u0000-\u001f\u007f]/.test(candidate.author), 'author'],
        [typeof candidate.terms === 'string' && candidate.terms.length >= 3 && candidate.terms.length <= 240 && LICENSE_TERMS.test(candidate.terms), 'terms'],
        [/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(acquiredAt) && !Number.isNaN(Date.parse(acquiredAt)), 'acquired_at'],
        [typeof candidate.license_text_path === 'string' && candidate.license_text_path.length >= 3 && candidate.license_text_path.length <= 240 && RELATIVE_PATH.test(candidate.license_text_path), 'license_text_path'],
        [typeof candidate.license_text_sha256 === 'string' && SHA256.test(candidate.license_text_sha256), 'license_text_sha256'],
      ];
      for (const [valid, field] of checks) {
        if (!valid) {
          issues.push(diagnostic(`${pointer}/${field}`, undefined, licenseId));
        }
      }
    });
  }
  return issues;
}

export interface ManifestLintOptions {
  approvedTerms: ReadonlySet<string>;
}

const RULE_LAYER_PATH_SEGMENTS = new Set([
  'collision',
  'walkability',
  'semantic',
]);

function isVisualMapAsset(assetId: string): boolean {
  return (
    assetId.startsWith('ground_art.') ||
    assetId.startsWith('asset.ground_art.') ||
    assetId.startsWith('structure.') ||
    assetId.startsWith('asset.structure.')
  );
}

function pointsIntoRuleLayer(path: string): boolean {
  return path
    .toLowerCase()
    .split('/')
    .some(segment => RULE_LAYER_PATH_SEGMENTS.has(segment));
}

export function lintManifest(
  manifest: AssetManifest,
  options: ManifestLintOptions,
): ManifestDiagnostic[] {
  const diagnostics: ManifestDiagnostic[] = [];
  const licenses = new Map<string, number>();
  manifest.licenses.forEach((license, index) => {
    if (licenses.has(license.license_id)) {
      diagnostics.push({
        code: 'RENDER_LICENSE_ID_DUPLICATE',
        pointer: `/licenses/${index}/license_id`,
        licenseId: license.license_id,
      });
    } else {
      licenses.set(license.license_id, index);
    }
    if (!options.approvedTerms.has(license.terms)) {
      diagnostics.push({
        code: 'RENDER_LICENSE_TERMS_UNAPPROVED',
        pointer: `/licenses/${index}/terms`,
        licenseId: license.license_id,
      });
    }
  });

  const assets = new Map<string, number>();
  const paths = new Map<string, string>();
  manifest.assets.forEach((asset, index) => {
    if (assets.has(asset.asset_id)) {
      diagnostics.push({
        code: 'RENDER_ASSET_ID_DUPLICATE',
        pointer: `/assets/${index}/asset_id`,
        assetId: asset.asset_id,
      });
    } else {
      assets.set(asset.asset_id, index);
    }
    if (paths.has(asset.path)) {
      diagnostics.push({
        code: 'RENDER_ASSET_PATH_DUPLICATE',
        pointer: `/assets/${index}/path`,
        assetId: asset.asset_id,
      });
    } else {
      paths.set(asset.path, asset.asset_id);
    }
    if (isVisualMapAsset(asset.asset_id) && pointsIntoRuleLayer(asset.path)) {
      diagnostics.push({
        code: 'RENDER_ASSET_PATH_INVALID',
        pointer: `/assets/${index}/path`,
        assetId: asset.asset_id,
      });
    }
    if (!licenses.has(asset.license_id)) {
      diagnostics.push({
        code: 'RENDER_LICENSE_RECORD_MISSING',
        pointer: `/assets/${index}/license_id`,
        assetId: asset.asset_id,
        licenseId: asset.license_id,
      });
    }
  });

  const colors = new Map<string, 0 | 1 | 2>();
  const visit = (assetId: string): void => {
    const color = colors.get(assetId) ?? 0;
    if (color === 1) {
      diagnostics.push({
        code: 'RENDER_FALLBACK_CYCLE',
        pointer: `/assets/${assets.get(assetId) ?? 0}/fallback_asset_id`,
        assetId,
      });
      return;
    }
    if (color === 2) {
      return;
    }
    colors.set(assetId, 1);
    const index = assets.get(assetId);
    if (index === undefined) {
      return;
    }
    const asset = manifest.assets[index];
    const fallbackIndex = assets.get(asset.fallback_asset_id);
    if (
      asset.fallback_asset_id === asset.asset_id ||
      fallbackIndex === undefined ||
      (fallbackIndex !== undefined &&
        manifest.assets[fallbackIndex].type !== asset.type) ||
      (asset.load_policy === 'required' &&
        fallbackIndex !== undefined &&
        manifest.assets[fallbackIndex].load_group !== 'group.global.required')
    ) {
      diagnostics.push({
        code: 'RENDER_FALLBACK_REFERENCE_INVALID',
        pointer: `/assets/${index}/fallback_asset_id`,
        assetId,
      });
    } else {
      visit(asset.fallback_asset_id);
    }
    colors.set(assetId, 2);
  };
  for (const asset of manifest.assets) {
    visit(asset.asset_id);
  }
  return diagnostics;
}

export type ManifestBytesResolver = (
  path: string,
) => Uint8Array | Promise<Uint8Array>;

export interface ManifestFileVerificationOptions {
  resolveBytes: ManifestBytesResolver;
  sha256?: (bytes: Uint8Array) => string | Promise<string>;
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest(
    'SHA-256',
    bytes.slice().buffer,
  );
  return Array.from(new Uint8Array(digest), byte =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

export async function verifyManifestFiles(
  manifest: AssetManifest,
  options: ManifestFileVerificationOptions,
): Promise<ManifestDiagnostic[]> {
  const diagnostics: ManifestDiagnostic[] = [];
  const computeSha256 = options.sha256 ?? sha256Hex;

  for (let index = 0; index < manifest.assets.length; index += 1) {
    const asset = manifest.assets[index];
    let bytes: Uint8Array;
    try {
      if (!RELATIVE_PATH.test(asset.path)) {
        throw new Error('invalid path');
      }
      bytes = await options.resolveBytes(asset.path);
      if (!(bytes instanceof Uint8Array)) {
        throw new Error('resolver returned non-bytes');
      }
    } catch {
      diagnostics.push({
        code: 'RENDER_ASSET_PATH_INVALID',
        pointer: `/assets/${index}/path`,
        assetId: asset.asset_id,
      });
      continue;
    }

    if (bytes.byteLength !== asset.byte_length) {
      diagnostics.push({
        code: 'RENDER_ASSET_HASH_MISMATCH',
        pointer: `/assets/${index}/byte_length`,
        assetId: asset.asset_id,
      });
    }
    const actualSha256 = await computeSha256(bytes);
    if (actualSha256 !== asset.sha256) {
      diagnostics.push({
        code: 'RENDER_ASSET_HASH_MISMATCH',
        pointer: `/assets/${index}/sha256`,
        assetId: asset.asset_id,
      });
    }
  }

  for (let index = 0; index < manifest.licenses.length; index += 1) {
    const license = manifest.licenses[index];
    let bytes: Uint8Array;
    try {
      if (!RELATIVE_PATH.test(license.license_text_path)) {
        throw new Error('invalid path');
      }
      bytes = await options.resolveBytes(license.license_text_path);
      if (!(bytes instanceof Uint8Array)) {
        throw new Error('resolver returned non-bytes');
      }
    } catch {
      diagnostics.push({
        code: 'RENDER_LICENSE_TEXT_PATH_INVALID',
        pointer: `/licenses/${index}/license_text_path`,
        licenseId: license.license_id,
      });
      continue;
    }

    const actualSha256 = await computeSha256(bytes);
    if (actualSha256 !== license.license_text_sha256) {
      diagnostics.push({
        code: 'RENDER_LICENSE_TEXT_HASH_MISMATCH',
        pointer: `/licenses/${index}/license_text_sha256`,
        licenseId: license.license_id,
      });
    }
  }

  return diagnostics;
}
