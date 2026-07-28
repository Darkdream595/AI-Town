import { describe, expect, it } from 'vitest';
import {
  ASSET_MANIFEST_SCHEMA,
  lintManifest,
  validateManifestSchema,
  verifyManifestFiles,
  type AssetManifest,
} from '../manifest';

const HASH_A = 'a'.repeat(64);
const HASH_B = 'b'.repeat(64);
const ABC_SHA256 =
  'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad';
const LICENSE_TEXT_SHA256 =
  '086ef1421303f033b3b925a9c783576ff65dc9d44a1aeadbd5fac5e61953ca26';

function validManifest(): AssetManifest {
  return {
    schema_version: 'asset-manifest.v1',
    assets: [
      {
        asset_id: 'sprite.resident.alice',
        type: 'image',
        path: 'assets/alice.png',
        sha256: HASH_A,
        byte_length: 10,
        load_group: 'group.global.required',
        load_policy: 'required',
        license_id: 'license.project.original',
        fallback_asset_id: 'sprite.fallback.silhouette',
      },
      {
        asset_id: 'sprite.fallback.silhouette',
        type: 'image',
        path: 'assets/fallback.png',
        sha256: HASH_B,
        byte_length: 12,
        load_group: 'group.global.required',
        load_policy: 'required',
        license_id: 'license.project.original',
        fallback_asset_id: 'sprite.fallback.checkerboard',
      },
      {
        asset_id: 'sprite.fallback.checkerboard',
        type: 'image',
        path: 'assets/checkerboard.png',
        sha256: HASH_A,
        byte_length: 8,
        load_group: 'group.global.required',
        load_policy: 'optional',
        license_id: 'license.project.original',
        fallback_asset_id: 'sprite.fallback.silhouette',
      },
    ],
    licenses: [
      {
        license_id: 'license.project.original',
        source_uri: 'project://assets',
        author: 'AI Town',
        terms: 'LicenseRef-Project-Original',
        acquired_at: '2026-07-28T00:00:00Z',
        license_text_path: 'licenses/project.txt',
        license_text_sha256: HASH_A,
      },
    ],
  };
}

describe('TEST-RENDER-011 asset manifest', () => {
  it('exposes the exact canonical schema id and rejects unknown fields', () => {
    expect(ASSET_MANIFEST_SCHEMA.$id).toBe(
      'https://ai-town.local/schemas/asset-manifest.v1.schema.json',
    );
    const manifest = {
      ...validManifest(),
      unknown: true,
    };
    expect(validateManifestSchema(manifest)[0].code).toBe(
      'RENDER_MANIFEST_SCHEMA_INVALID',
    );
  });

  it('exposes the complete canonical schema constraints', () => {
    expect(ASSET_MANIFEST_SCHEMA.title).toBe('AI Town Asset Manifest v1');
    expect(ASSET_MANIFEST_SCHEMA.properties.assets.items.$ref).toBe(
      '#/$defs/AssetManifestEntry',
    );
    expect(ASSET_MANIFEST_SCHEMA.$defs.AssetManifestEntry.required).toContain(
      'fallback_asset_id',
    );
    expect(
      ASSET_MANIFEST_SCHEMA.$defs.LicenseRecord.properties.acquired_at,
    ).toEqual({ type: 'string', format: 'date-time' });
  });

  it('validates uri, date-time, stable ids and normalized paths', () => {
    const manifest = validManifest();
    manifest.assets[0].path = '../escape.png';
    manifest.licenses[0].source_uri = 'javascript:alert(1)';
    manifest.licenses[0].acquired_at = 'not-a-date';
    expect(validateManifestSchema(manifest).length).toBeGreaterThanOrEqual(3);
  });

  it('enforces canonical length, integer and license term bounds', () => {
    const manifest = validManifest();
    manifest.assets[0].asset_id = `sprite.${'a'.repeat(154)}`;
    manifest.assets[0].byte_length = 2_147_483_648;
    manifest.licenses[0].source_uri = `https://example.com/${'a'.repeat(2040)}`;
    manifest.licenses[0].terms = 'invalid/terms';

    const pointers = validateManifestSchema(manifest).map(
      diagnostic => diagnostic.pointer,
    );
    expect(pointers).toContain('/assets/0/asset_id');
    expect(pointers).toContain('/assets/0/byte_length');
    expect(pointers).toContain('/licenses/0/source_uri');
    expect(pointers).toContain('/licenses/0/terms');
  });

  it('enforces canonical uniqueItems for records', () => {
    const manifest = validManifest();
    manifest.assets.push({ ...manifest.assets[0] });
    manifest.licenses.push({ ...manifest.licenses[0] });

    const pointers = validateManifestSchema(manifest).map(
      diagnostic => diagnostic.pointer,
    );
    expect(pointers).toContain('/assets/3');
    expect(pointers).toContain('/licenses/1');
  });

  it('reports duplicate ids, missing licenses and unapproved terms', () => {
    const manifest = validManifest();
    manifest.assets[1].asset_id = manifest.assets[0].asset_id;
    manifest.assets[0].license_id = 'license.missing.record';
    manifest.licenses[0].terms = 'Forbidden Custom Terms';
    const diagnostics = lintManifest(manifest, {
      approvedTerms: new Set(['LicenseRef-Project-Original']),
    });
    expect(diagnostics.map(item => item.code)).toEqual(
      expect.arrayContaining([
        'RENDER_ASSET_ID_DUPLICATE',
        'RENDER_LICENSE_RECORD_MISSING',
        'RENDER_LICENSE_TERMS_UNAPPROVED',
      ]),
    );
  });

  it('detects fallback cycles and self references', () => {
    const manifest = validManifest();
    const diagnostics = lintManifest(manifest, {
      approvedTerms: new Set(['LicenseRef-Project-Original']),
    });
    expect(diagnostics.map(item => item.code)).toContain(
      'RENDER_FALLBACK_CYCLE',
    );
    manifest.assets[0].fallback_asset_id = manifest.assets[0].asset_id;
    expect(
      lintManifest(manifest, {
        approvedTerms: new Set(['LicenseRef-Project-Original']),
      }).map(item => item.code),
    ).toContain('RENDER_FALLBACK_REFERENCE_INVALID');
  });

  it('verifies actual asset and license bytes with SHA-256', async () => {
    const manifest = validManifest();
    manifest.assets[0].sha256 = ABC_SHA256;
    manifest.assets[0].byte_length = 3;
    manifest.licenses[0].license_text_sha256 = LICENSE_TEXT_SHA256;
    const files = new Map<string, Uint8Array>([
      ['assets/alice.png', new TextEncoder().encode('abc')],
      ['assets/fallback.png', new TextEncoder().encode('fallback')],
      ['assets/checkerboard.png', new TextEncoder().encode('fallback')],
      ['licenses/project.txt', new TextEncoder().encode('license text')],
    ]);
    manifest.assets[1].sha256 =
      '5c7ee2074b65853f71fc5a01ce194ff26deedf6daacdb715c6beefdfd3f31b35';
    manifest.assets[1].byte_length = 8;
    manifest.assets[2].sha256 = manifest.assets[1].sha256;
    manifest.assets[2].byte_length = 8;

    await expect(
      verifyManifestFiles(manifest, {
        resolveBytes: path => {
          const bytes = files.get(path);
          if (!bytes) {
            throw new Error('missing');
          }
          return bytes;
        },
      }),
    ).resolves.toEqual([]);
  });

  it('reports stable pointers for missing, wrong-length and wrong-hash assets', async () => {
    const manifest = validManifest();
    manifest.assets[0].byte_length = 4;
    manifest.assets[0].sha256 = HASH_A;
    const diagnostics = await verifyManifestFiles(manifest, {
      resolveBytes: path => {
        if (path === 'assets/alice.png') {
          return new TextEncoder().encode('abc');
        }
        throw new Error('SECRET FILE CONTENT');
      },
    });

    expect(diagnostics).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'RENDER_ASSET_HASH_MISMATCH',
          pointer: '/assets/0/byte_length',
          assetId: 'sprite.resident.alice',
        }),
        expect.objectContaining({
          code: 'RENDER_ASSET_HASH_MISMATCH',
          pointer: '/assets/0/sha256',
          assetId: 'sprite.resident.alice',
        }),
        expect.objectContaining({
          code: 'RENDER_ASSET_PATH_INVALID',
          pointer: '/assets/1/path',
          assetId: 'sprite.fallback.silhouette',
        }),
        expect.objectContaining({
          code: 'RENDER_LICENSE_TEXT_PATH_INVALID',
          pointer: '/licenses/0/license_text_path',
          licenseId: 'license.project.original',
        }),
      ]),
    );
    expect(JSON.stringify(diagnostics)).not.toContain('SECRET FILE CONTENT');
  });

  it('reports license evidence failures without leaking file contents', async () => {
    const manifest = validManifest();
    const diagnostics = await verifyManifestFiles(manifest, {
      resolveBytes: path => {
        if (path === 'licenses/project.txt') {
          return new TextEncoder().encode('PRIVATE LICENSE CONTENT');
        }
        return new TextEncoder().encode('asset');
      },
    });

    expect(diagnostics).toContainEqual({
      code: 'RENDER_LICENSE_TEXT_HASH_MISMATCH',
      pointer: '/licenses/0/license_text_sha256',
      licenseId: 'license.project.original',
    });
    expect(JSON.stringify(diagnostics)).not.toContain(
      'PRIVATE LICENSE CONTENT',
    );
  });

  it('requires required-group fallbacks to be preloadable', () => {
    const manifest = validManifest();
    manifest.assets[0].load_group = 'group.scene.required';
    manifest.assets[1].load_group = 'group.scene.other';

    expect(
      lintManifest(manifest, {
        approvedTerms: new Set(['LicenseRef-Project-Original']),
      }),
    ).toContainEqual({
      code: 'RENDER_FALLBACK_REFERENCE_INVALID',
      pointer: '/assets/0/fallback_asset_id',
      assetId: 'sprite.resident.alice',
    });
  });

  it.each([
    ['ground_art.region.tile', 'maps/collision/crown-creek.json'],
    ['structure.house.wall', 'maps/semantic/houses.json'],
    ['structure.bridge.deck', 'maps/walkability/bridge.json'],
  ])(
    'rejects visual asset %s pointing into a rule-layer path',
    (assetId, path) => {
      const manifest = validManifest();
      manifest.assets[0].asset_id = assetId;
      manifest.assets[0].path = path;

      expect(
        lintManifest(manifest, {
          approvedTerms: new Set(['LicenseRef-Project-Original']),
        }),
      ).toContainEqual({
        code: 'RENDER_ASSET_PATH_INVALID',
        pointer: '/assets/0/path',
        assetId,
      });
    },
  );
});
