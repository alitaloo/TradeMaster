#!/usr/bin/env node
/**
 * TradeMaster Gateway Version Sync
 * 自動確保 Gateway 版本與 OpenClaw 一致
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const COLORS = {
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  red: '\x1b[31m',
  reset: '\x1b[0m'
};

function log(msg, color = 'reset') {
  console.log(`${COLORS[color]}${msg}${COLORS.reset}`);
}

function getOpenclawVersion() {
  try {
    return execSync('npm view openclaw version', { encoding: 'utf8' }).trim();
  } catch {
    return null;
  }
}

function getInstalledVersion() {
  try {
    const configPath = path.join(
      process.env.APPDATA || path.join(process.env.HOME, '.config'),
      '.openclaw/openclaw.json'
    );
    
    if (fs.existsSync(configPath)) {
      const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      return config.meta?.lastTouchedVersion || null;
    }
  } catch {
    // ignore
  }
  return null;
}

function syncGateway() {
  log('🔄 同步 Gateway 版本...', 'yellow');
  
  try {
    execSync('openclaw gateway restart', { stdio: 'inherit' });
    log('✅ Gateway 已更新', 'green');
    return true;
  } catch (err) {
    log(`❌ Gateway 更新失敗: ${err.message}`, 'red');
    return false;
  }
}

async function main() {
  log('📊 檢查 Gateway 版本...\n');
  
  const currentVersion = getOpenclawVersion();
  const configVersion = getInstalledVersion();
  
  log(`OpenClaw 版本: ${currentVersion || '未知'}`);
  log(`配置版本: ${configVersion || '未知'}\n`);
  
  if (currentVersion && configVersion && currentVersion !== configVersion) {
    log('⚠️ 版本不一致，自動同步中...', 'yellow');
    
    if (syncGateway()) {
      log('\n✅ 版本同步完成！', 'green');
      process.exit(0);
    } else {
      log('\n❌ 版本同步失敗，請手動執行: openclaw gateway restart', 'red');
      process.exit(1);
    }
  } else {
    log('✅ 版本一致，無需更新', 'green');
    process.exit(0);
  }
}

main();
