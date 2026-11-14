import { defineConfig, devices } from '@playwright/test';
const baseURL = `http://127.0.0.1:${process.env.OPENARMS_FIXTURE_PORT || 8766}`;
export default defineConfig({
  testDir: '.', testMatch:'browser.spec.mjs', timeout:30000, expect:{timeout:7000}, fullyParallel:false,
  use:{baseURL,trace:'retain-on-failure',screenshot:'only-on-failure',launchOptions:{args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']}},
  projects:[{name:'desktop',use:{...devices['Desktop Chrome'],viewport:{width:1440,height:1000}}},{name:'mobile-chromium',use:{...devices['iPhone 13'],defaultBrowserType:'chromium'}}],
  webServer:{command:'node fixture-server.mjs',url:baseURL,reuseExistingServer:false},
});
