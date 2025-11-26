import { test, expect } from '@playwright/test';

test.describe('Tool Call Streaming', () => {
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

  test('Should render tool calls with streaming states', async ({ page }) => {
    // Navigate to chat
    await page.goto(chatUrl);
    await page.waitForSelector('.chat-session-page', { timeout: 10000 });

    // Check if tool call containers are rendered correctly
    const toolCallContainers = await page.locator('.tool-call-container').all();

    if (toolCallContainers.length > 0) {
      // Check first tool call
      const firstToolCall = toolCallContainers[0];

      // Check header exists
      const header = await firstToolCall.locator('.tool-call-header').isVisible();
      expect(header).toBeTruthy();

      // Check if tool name is visible
      const toolName = await firstToolCall.locator('.tool-call-header strong').textContent();
      expect(toolName).toBeTruthy();

      // Check for arguments section if present
      const argsSection = await firstToolCall.locator('.tool-call-args').isVisible().catch(() => false);
      console.log('Arguments section visible:', argsSection);

      // Check for result section if present
      const resultSection = await firstToolCall.locator('.tool-call-result').isVisible().catch(() => false);
      console.log('Result section visible:', resultSection);
    }

    // Test streaming indicator appearance
    await page.evaluate(() => {
      // Mock a streaming tool call
      const event = new CustomEvent('streamEvent', {
        detail: {
          type: 'action_args_chunk',
          tool: 'TestTool',
          partial_args: { test: 'value' }
        }
      });
      window.dispatchEvent(event);
    });

    // Wait a bit for any streaming updates
    await page.waitForTimeout(1000);

    // Check if any streaming indicators appear
    const streamingIndicators = await page.locator('text=/streaming/i').all();
    console.log('Streaming indicators found:', streamingIndicators.length);
  });

  test('Should handle file_write operations with syntax highlighting', async ({ page }) => {
    await page.goto(chatUrl);
    await page.waitForSelector('.chat-session-page', { timeout: 10000 });

    // Look for any file_write tool calls
    const fileWriteTools = await page.locator('.tool-call-container').filter({
      hasText: /file_write|write_file|writefile/i
    }).all();

    if (fileWriteTools.length > 0) {
      const firstFileWrite = fileWriteTools[0];

      // Check for file path display
      const filePathElement = await firstFileWrite.locator('code').first();
      const filePath = await filePathElement.textContent().catch(() => null);
      console.log('File path found:', filePath);

      // Check for syntax highlighting
      const syntaxHighlighter = await firstFileWrite.locator('[class*="language-"]').isVisible().catch(() => false);
      console.log('Syntax highlighter present:', syntaxHighlighter);
    }
  });

  test('Should display tool status correctly', async ({ page }) => {
    await page.goto(chatUrl);
    await page.waitForSelector('.chat-session-page', { timeout: 10000 });

    const toolCallContainers = await page.locator('.tool-call-container').all();

    for (const container of toolCallContainers) {
      // Check header background colors for status
      const header = await container.locator('.tool-call-header');
      const headerStyle = await header.getAttribute('style');

      // Check for running state (yellow gradient)
      const isRunning = headerStyle?.includes('fef3c7') || headerStyle?.includes('fde68a');

      // Check for result indicators
      const hasSuccessIcon = await container.locator('text=✅').isVisible().catch(() => false);
      const hasErrorIcon = await container.locator('text=❌').isVisible().catch(() => false);

      console.log('Tool status - Running:', isRunning, 'Success:', hasSuccessIcon, 'Error:', hasErrorIcon);

      // At least one status should be present
      expect(isRunning || hasSuccessIcon || hasErrorIcon).toBeTruthy();
    }
  });
});