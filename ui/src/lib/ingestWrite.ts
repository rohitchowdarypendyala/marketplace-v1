import { db } from './db';
import { extractHandle, type Platform } from './platformDetect';
import { spawn } from 'node:child_process';
import path from 'node:path';

function nowIso() {
  return new Date().toISOString();
}

export async function upsertCreatorAndProfile(platform: Platform, normalizedProfileUrl: string): Promise<{
  creator_id: number;
  social_profile_id: number;
}> {
  const d = db();

  const existing = d
    .prepare(
      `SELECT id, creator_id
       FROM social_profiles
       WHERE platform = ? AND profile_url = ?
       LIMIT 1`
    )
    .get(platform, normalizedProfileUrl) as any;

  if (existing) {
    return {
      social_profile_id: Number(existing.id),
      creator_id: Number(existing.creator_id),
    };
  }

  const handle = extractHandle(platform, normalizedProfileUrl);
  const primaryName = handle ? handle : normalizedProfileUrl;

  // Create creator
  const createdAt = nowIso();
  d.prepare(`INSERT INTO creators(primary_name, linktree_domain, created_at) VALUES(?,?,?)`).run(
    primaryName,
    null,
    createdAt
  );

  const creatorRow = d.prepare(`SELECT last_insert_rowid() as id`).get() as any;
  const creator_id = Number(creatorRow.id);

  // Create social profile (minimal required fields + admin-added tagging via trust_flags)
  d.prepare(
    `INSERT INTO social_profiles(
      creator_id, platform, profile_url, handle, display_name,
      created_at, last_fetched_at, updated_at,
      trust_flags
    ) VALUES(?,?,?,?,?,?,?,?,?)`
  ).run(
    creator_id,
    platform,
    normalizedProfileUrl,
    handle,
    handle,
    createdAt,
    null,
    createdAt,
    JSON.stringify(['admin_added'])
  );

  const spRow = d.prepare(`SELECT last_insert_rowid() as id`).get() as any;
  const social_profile_id = Number(spRow.id);

  return { creator_id, social_profile_id };
}

function pythonCmd(): string {
  // Prefer workspace venv python; fallback to python3.
  const venvPy = '/home/rohit_chowdary/Rohit-AI-WorkSpace/.venv/bin/python';
  return venvPy;
}

export async function runIngestion(platform: Platform, normalizedProfileUrl: string): Promise<{ ok: true }>{
  const scriptsDir = '/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/scripts';
  const py = pythonCmd();

  let scriptPath = '';
  let args: string[] = [];

  if (platform === 'instagram') {
    scriptPath = path.join(scriptsDir, 'instagram_ingest_playwright.py');
    args = [
      '-u',
      scriptPath,
      '--accurate-metrics',
      '--last-n',
      '10',
      '--profile-url',
      normalizedProfileUrl,
    ];
  } else {
    scriptPath = path.join(scriptsDir, 'youtube_ingest.py');
    args = ['-u', scriptPath, '--accurate-metrics', normalizedProfileUrl];
  }

  await new Promise<void>((resolve, reject) => {
    const child = spawn(py, args, {
      cwd: scriptsDir,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        // Ensure script uses the correct DB path if supported via env
        MARKETPLACE_DB_PATH: '/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db',
      },
    });

    let stderr = '';
    child.stdout.on('data', (d) => {
      // Keep logs for demo visibility
      process.stdout.write(String(d));
    });
    child.stderr.on('data', (d) => {
      stderr += String(d);
      process.stderr.write(String(d));
    });
    child.on('error', (err) => reject(err));
    child.on('close', (code) => {
      if (code === 0) return resolve();
      reject(new Error(`Ingestion failed (exit ${code}). ${stderr.slice(0, 2000)}`));
    });
  });

  return { ok: true };
}

export async function addAndIngest(platform: Platform, normalizedProfileUrl: string) {
  const ids = await upsertCreatorAndProfile(platform, normalizedProfileUrl);
  await runIngestion(platform, normalizedProfileUrl);
  return ids;
}
