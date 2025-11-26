import { test, expect } from '@playwright/test';

test.describe('JSON Parsing Error Fix', () => {
  const projectId = 'f75e06b1-bb07-430c-b82c-a0871adc67f4';
  const sessionId = '788de109-52ce-42e1-bc38-df28412f9d9f';
  const chatUrl = `http://localhost:5174/projects/${projectId}/chat/${sessionId}`;

  test.beforeEach(async ({ page }) => {
    // Enable assistant-ui
    await page.goto('http://localhost:5174/');
    await page.evaluate(() => {
      localStorage.setItem('enableAssistantUI', 'true');
    });
  });

  test('Should handle partial JSON during tool streaming without crashing', async ({ page }) => {
    // Collect console errors
    const jsErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text();
        // Filter out expected CORS/network errors
        if (!text.includes('CORS') &&
            !text.includes('Failed to load resource') &&
            !text.includes('WebSocket') &&
            !text.includes('XMLHttpRequest')) {
          jsErrors.push(text);
        }
      }
    });

    // Navigate to chat
    await page.goto(chatUrl);
    await page.waitForSelector('.chat-session-page', { timeout: 10000 });

    // Simulate partial JSON in streaming (this would normally come from WebSocket)
    await page.evaluate(() => {
      // Create a mock streaming event with partial JSON
      const event = new CustomEvent('streamEvent', {
        detail: {
          type: 'action_args_chunk',
          tool: 'file_write',
          // This is intentionally partial/invalid JSON
          partial_args: '{"file_path": "/test.py", "content": "def hello'
        }
      });

      // Dispatch the event to trigger the rendering
      window.dispatchEvent(event);
    });

    // Wait a bit for React to process
    await page.waitForTimeout(500);

    // Check that the page didn't crash (no black screen)
    const chatPageVisible = await page.locator('.chat-session-page').isVisible();
    const headerVisible = await page.locator('.chat-header').isVisible().catch(() => false);
    const inputVisible = await page.locator('.chat-input').isVisible().catch(() => false);

    // Check for JSON parsing errors
    const hasJsonError = jsErrors.some(err =>
      err.includes('JSON') ||
      err.includes('Unterminated string') ||
      err.includes('Unexpected token')
    );

    console.log('JS Errors found:', jsErrors);
    console.log('Chat page visible after partial JSON:', chatPageVisible);
    console.log('Header visible:', headerVisible);
    console.log('Input visible:', inputVisible);

    // Assertions
    expect(hasJsonError, 'Should not have JSON parsing errors').toBeFalsy();
    expect(chatPageVisible, 'Chat page should remain visible').toBeTruthy();
    expect(headerVisible, 'Header should remain visible').toBeTruthy();
    expect(inputVisible, 'Input should remain visible').toBeTruthy();
  });

  test('Should handle complete JSON after partial streaming', async ({ page }) => {
    await page.goto(chatUrl);
    await page.waitForSelector('.chat-session-page', { timeout: 10000 });

    // Simulate progression from partial to complete JSON
    await page.evaluate(() => {
      // First, partial JSON
      let event = new CustomEvent('streamEvent', {
        detail: {
          type: 'action_args_chunk',
          tool: 'file_write',
          partial_args: '{"file_path": "/test.py'
        }
      });
      window.dispatchEvent(event);

      // Then, more complete but still partial
      event = new CustomEvent('streamEvent', {
        detail: {
          type: 'action_args_chunk',
          tool: 'file_write',
          partial_args: '{"file_path": "/test.py", "content":'
        }
      });
      window.dispatchEvent(event);

      // Finally, complete JSON
      event = new CustomEvent('streamEvent', {
        detail: {
          type: 'action',
          tool: 'file_write',
          args: { file_path: '/test.py', content: 'def hello():\n    print("Hello")' }
        }
      });
      window.dispatchEvent(event);
    });

    await page.waitForTimeout(500);

    // Check that the page is still functioning
    const chatPageVisible = await page.locator('.chat-session-page').isVisible();
    expect(chatPageVisible).toBeTruthy();

    // Check if tool call containers exist (if any messages with tools are present)
    const toolCallContainers = await page.locator('.tool-call-container').count();
    console.log('Tool call containers found:', toolCallContainers);
  });
});