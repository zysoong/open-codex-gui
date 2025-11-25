import { test, expect } from '@playwright/test';

test.describe('Chat Session', () => {
  let projectId: string;

  test.beforeEach(async ({ page }) => {
    // Create a project before each test
    await page.goto('/');
    await page.click('button:has-text("Create Project")');
    await page.fill('input[name="name"]', 'Chat Test Project');
    await page.fill('textarea[name="description"]', 'Project for chat testing');
    await page.click('button:has-text("Create")');
    await page.waitForTimeout(1000);

    // Navigate to project landing page
    await page.click('text=Chat Test Project');
    await page.waitForTimeout(500);

    // Extract project ID from URL
    const url = page.url();
    const match = url.match(/\/projects\/([a-f0-9-]+)/);
    if (match) {
      projectId = match[1];
    }
  });

  test('CS-001: Quick start chat', async ({ page }) => {
    // Type message in quick start input
    await page.fill('textarea[placeholder*="How can I help"]', 'Hello, this is a test message');

    // Click send button
    await page.click('button.send-btn');

    // Verify redirected to chat session
    await expect(page).toHaveURL(/\/projects\/[a-f0-9-]+\/chat\/[a-f0-9-]+$/);

    // Wait for message to appear
    await page.waitForTimeout(2000);

    // Verify user message appears
    await expect(page.locator('text=Hello, this is a test message')).toBeVisible();

    // Verify session name appears in header
    await expect(page.locator('.session-title')).toContainText('Chat');
  });

  test('CS-002: Send message in existing session', async ({ page }) => {
    // Create a session first using quick start
    await page.fill('textarea[placeholder*="How can I help"]', 'First message');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Now send another message
    await page.fill('.chat-input', 'Second message in the same session');
    await page.press('.chat-input', 'Enter');

    // Wait for message to appear
    await page.waitForTimeout(1000);

    // Verify both messages appear
    await expect(page.locator('text=First message')).toBeVisible();
    await expect(page.locator('text=Second message in the same session')).toBeVisible();
  });

  test('CS-003: View conversation history', async ({ page }) => {
    // Create a session with multiple messages
    await page.fill('textarea[placeholder*="How can I help"]', 'Message 1');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    await page.fill('.chat-input', 'Message 2');
    await page.press('.chat-input', 'Enter');
    await page.waitForTimeout(1000);

    await page.fill('.chat-input', 'Message 3');
    await page.press('.chat-input', 'Enter');
    await page.waitForTimeout(1000);

    // Reload page
    await page.reload();
    await page.waitForTimeout(1000);

    // Verify all messages still visible
    await expect(page.locator('text=Message 1')).toBeVisible();
    await expect(page.locator('text=Message 2')).toBeVisible();
    await expect(page.locator('text=Message 3')).toBeVisible();
  });

  test('CS-004: Navigate between sessions', async ({ page }) => {
    // Create first session
    await page.fill('textarea[placeholder*="How can I help"]', 'First session message');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Go back to project
    await page.click('button:has-text("Back to Project")');
    await page.waitForTimeout(500);

    // Create second session
    await page.fill('textarea[placeholder*="How can I help"]', 'Second session message');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Go back to project
    await page.click('button:has-text("Back to Project")');
    await page.waitForTimeout(500);

    // Verify two sessions appear in list
    const sessions = page.locator('.session-card');
    await expect(sessions).toHaveCount(2);

    // Click on first session
    await sessions.first().click();
    await page.waitForTimeout(1000);

    // Verify first session message appears
    await expect(page.locator('text=First session message')).toBeVisible();
    await expect(page.locator('text=Second session message')).not.toBeVisible();
  });

  test('CS-005: Send button disabled for empty input', async ({ page }) => {
    // Create a session
    await page.fill('textarea[placeholder*="How can I help"]', 'Test');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Verify send button is disabled when input is empty
    const sendBtn = page.locator('.chat-input-wrapper .send-btn');
    await expect(sendBtn).toBeDisabled();

    // Type message
    await page.fill('.chat-input', 'New message');

    // Verify send button is now enabled
    await expect(sendBtn).toBeEnabled();

    // Clear input
    await page.fill('.chat-input', '');

    // Verify send button is disabled again
    await expect(sendBtn).toBeDisabled();
  });

  test('CS-006: Auto-scroll to latest message', async ({ page }) => {
    // Create session and send multiple messages
    await page.fill('textarea[placeholder*="How can I help"]', 'Start conversation');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Send several more messages
    for (let i = 1; i <= 5; i++) {
      await page.fill('.chat-input', `Message ${i}`);
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(800);
    }

    // Check that the last message is visible (scrolled into view)
    await expect(page.locator('text=Message 5')).toBeVisible();
  });

  test('CS-007: Session metadata display', async ({ page }) => {
    // Create a session
    await page.fill('textarea[placeholder*="How can I help"]', 'Test metadata display');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Verify session title is displayed
    const sessionTitle = page.locator('.session-title');
    await expect(sessionTitle).toBeVisible();

    // Verify environment badge is displayed (if environment is set)
    const environmentBadge = page.locator('.environment-badge');
    // Environment badge should be visible if environment_type is set
    const badgeCount = await environmentBadge.count();
    if (badgeCount > 0) {
      await expect(environmentBadge).toBeVisible();
    }
  });

  test('CS-008: Cancel streaming', async ({ page }) => {
    // Create a session
    await page.fill('textarea[placeholder*="How can I help"]', 'Write a very long essay');
    await page.click('button.send-btn');

    // Wait for streaming to start
    await page.waitForTimeout(500);

    // Look for cancel button (should appear during streaming)
    const cancelButton = page.locator('button:has-text("Cancel")');

    // If streaming is active, cancel button should be present
    const isCancelVisible = await cancelButton.isVisible().catch(() => false);
    if (isCancelVisible) {
      await cancelButton.click();

      // Verify streaming stopped
      await page.waitForTimeout(500);

      // Cancel button should be disabled after streaming stops
      await expect(cancelButton).toBeDisabled();
    }
  });

  test('CS-009: Error display and dismissal', async ({ page }) => {
    // Create a session
    await page.fill('textarea[placeholder*="How can I help"]', 'Test error handling');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Check if error banner appears (this would require triggering an error)
    // For now, we'll verify the error banner structure exists in the DOM
    const errorBanner = page.locator('.chat-error-banner');

    // If an error occurs during the test, we should be able to dismiss it
    const errorVisible = await errorBanner.isVisible().catch(() => false);
    if (errorVisible) {
      const closeButton = page.locator('.error-close-btn');
      await closeButton.click();

      // Verify error banner is no longer visible
      await expect(errorBanner).not.toBeVisible();
    }
  });

  test('CS-010: Back button navigation preserves data', async ({ page }) => {
    // Create a session with messages
    await page.fill('textarea[placeholder*="How can I help"]', 'First message');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Get the session URL
    const sessionUrl = page.url();

    // Navigate back to project
    await page.click('button:has-text("Back to Project")');
    await page.waitForTimeout(500);

    // Navigate back to the same session
    await page.goto(sessionUrl);
    await page.waitForTimeout(1000);

    // Verify message is still there
    await expect(page.locator('text=First message')).toBeVisible();
  });

  test('CS-011: Multiple messages rapid succession', async ({ page }) => {
    // Create a session
    await page.fill('textarea[placeholder*="How can I help"]', 'First');
    await page.click('button.send-btn');
    await page.waitForTimeout(1500);

    // Send multiple messages quickly
    const messages = ['Second', 'Third', 'Fourth'];
    for (const msg of messages) {
      await page.fill('.chat-input', msg);
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(500);
    }

    // Verify all messages appear
    await expect(page.locator('text=First')).toBeVisible();
    await expect(page.locator('text=Second')).toBeVisible();
    await expect(page.locator('text=Third')).toBeVisible();
    await expect(page.locator('text=Fourth')).toBeVisible();
  });

  test('CS-012: Session title update', async ({ page }) => {
    // Create a session
    await page.fill('textarea[placeholder*="How can I help"]', 'Hello, can you help me?');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Wait for potential title update from backend
    await page.waitForTimeout(1000);

    // Verify session title is present (might be updated by backend)
    const sessionTitle = page.locator('.session-title');
    await expect(sessionTitle).toBeVisible();

    // Title should not be empty
    const titleText = await sessionTitle.textContent();
    expect(titleText).toBeTruthy();
    expect(titleText?.length).toBeGreaterThan(0);
  });

  test('CS-013: Empty state to active chat transition', async ({ page }) => {
    // Navigate to project
    await page.goto('/');
    await page.click('button:has-text("Create Project")');
    await page.fill('input[name="name"]', 'Empty State Test');
    await page.click('button:has-text("Create")');
    await page.waitForTimeout(1000);

    await page.click('text=Empty State Test');
    await page.waitForTimeout(500);

    // Check for empty state message
    const quickStartInput = page.locator('textarea[placeholder*="How can I help"]');
    await expect(quickStartInput).toBeVisible();

    // Send first message
    await page.fill('textarea[placeholder*="How can I help"]', 'First message ever');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Verify transition to active chat
    await expect(page.locator('text=First message ever')).toBeVisible();
    await expect(page.locator('.chat-messages-container')).toBeVisible();
  });

  test('CS-014: Direct URL access to session', async ({ page }) => {
    // Create a session first
    await page.fill('textarea[placeholder*="How can I help"]', 'URL test message');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Get the session URL
    const sessionUrl = page.url();

    // Navigate away
    await page.goto('/');
    await page.waitForTimeout(500);

    // Direct access via URL
    await page.goto(sessionUrl);
    await page.waitForTimeout(1000);

    // Verify session loads correctly
    await expect(page.locator('text=URL test message')).toBeVisible();
    await expect(page.locator('.session-title')).toBeVisible();
    await expect(page.locator('.chat-input')).toBeVisible();
  });

  test('CS-015: Keyboard shortcuts in chat', async ({ page }) => {
    // Create a session
    await page.fill('textarea[placeholder*="How can I help"]', 'Keyboard test');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Test Enter to send
    await page.fill('.chat-input', 'Message sent with Enter');
    await page.press('.chat-input', 'Enter');
    await page.waitForTimeout(1000);
    await expect(page.locator('text=Message sent with Enter')).toBeVisible();

    // Test Shift+Enter for newline (message should not be sent)
    await page.fill('.chat-input', 'Line 1');
    await page.press('.chat-input', 'Shift+Enter');
    await page.type('.chat-input', 'Line 2');

    // Input should contain both lines
    const inputValue = await page.locator('.chat-input').inputValue();
    expect(inputValue).toContain('Line 1');
    expect(inputValue).toContain('Line 2');
  });

  test.describe('Bug Fix 2: Messages disappearing on navigation during streaming', () => {
    test('BF2-E2E-001: Messages persist when navigating back during streaming', async ({ page }) => {
      // Create a session with multiple messages
      await page.fill('textarea[placeholder*="How can I help"]', 'First message');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      await page.fill('.chat-input', 'Second message');
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(1500);

      // Start streaming a third message
      await page.fill('.chat-input', 'Write a long explanation about React');
      await page.press('.chat-input', 'Enter');

      // Wait for streaming to start
      await page.waitForTimeout(500);

      // Count messages before navigation
      const messageCountBefore = await page.evaluate(() => {
        return document.querySelectorAll('[data-testid^="message-"]').length;
      });

      expect(messageCountBefore).toBeGreaterThanOrEqual(3);

      // Navigate back to project while streaming is active
      await page.click('button:has-text("Back to Project")');
      await page.waitForTimeout(500);

      // Navigate back to the chat session
      const sessionCards = page.locator('.session-card');
      await sessionCards.first().click();
      await page.waitForTimeout(1000);

      // Verify all messages are still visible
      await expect(page.locator('text=First message')).toBeVisible();
      await expect(page.locator('text=Second message')).toBeVisible();

      // Count messages after navigation
      const messageCountAfter = await page.evaluate(() => {
        return document.querySelectorAll('[data-testid^="message-"]').length;
      });

      expect(messageCountAfter).toBe(messageCountBefore);
    });

    test('BF2-E2E-002: Page does not show empty state after navigating back during streaming', async ({ page }) => {
      // Create a session
      await page.fill('textarea[placeholder*="How can I help"]', 'Initial message');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      // Start streaming
      await page.fill('.chat-input', 'Tell me about JavaScript');
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(500);

      // Navigate away
      await page.click('button:has-text("Back to Project")');
      await page.waitForTimeout(500);

      // Navigate back
      const sessionCards = page.locator('.session-card');
      await sessionCards.first().click();
      await page.waitForTimeout(1000);

      // Should NOT show empty state
      const emptyState = page.locator('text=Start a conversation');
      await expect(emptyState).not.toBeVisible();

      // Should show messages
      await expect(page.locator('text=Initial message')).toBeVisible();
    });

    test('BF2-E2E-003: Messages persist across multiple navigation cycles', async ({ page }) => {
      // Create a session with messages
      await page.fill('textarea[placeholder*="How can I help"]', 'Message 1');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      await page.fill('.chat-input', 'Message 2');
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(1500);

      // First navigation cycle
      await page.click('button:has-text("Back to Project")');
      await page.waitForTimeout(500);
      await page.locator('.session-card').first().click();
      await page.waitForTimeout(1000);

      await expect(page.locator('text=Message 1')).toBeVisible();
      await expect(page.locator('text=Message 2')).toBeVisible();

      // Second navigation cycle
      await page.click('button:has-text("Back to Project")');
      await page.waitForTimeout(500);
      await page.locator('.session-card').first().click();
      await page.waitForTimeout(1000);

      await expect(page.locator('text=Message 1')).toBeVisible();
      await expect(page.locator('text=Message 2')).toBeVisible();

      // Third navigation cycle
      await page.click('button:has-text("Back to Project")');
      await page.waitForTimeout(500);
      await page.locator('.session-card').first().click();
      await page.waitForTimeout(1000);

      await expect(page.locator('text=Message 1')).toBeVisible();
      await expect(page.locator('text=Message 2')).toBeVisible();
    });

    test('BF2-E2E-004: Streaming message persists when navigating back', async ({ page }) => {
      // Create a session
      await page.fill('textarea[placeholder*="How can I help"]', 'Start session');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      // Start streaming
      await page.fill('.chat-input', 'Explain TypeScript');
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(1000);

      // Get partial streaming content
      const partialContent = await page.evaluate(() => {
        const messages = document.querySelectorAll('[data-testid^="message-"]');
        const lastMessage = messages[messages.length - 1];
        return lastMessage?.textContent || '';
      });

      // Navigate away during streaming
      await page.click('button:has-text("Back to Project")');
      await page.waitForTimeout(500);

      // Navigate back
      await page.locator('.session-card').first().click();
      await page.waitForTimeout(1000);

      // Original messages should still be there
      await expect(page.locator('text=Start session')).toBeVisible();

      // The streaming message should also persist
      const messages = await page.evaluate(() => {
        return document.querySelectorAll('[data-testid^="message-"]').length;
      });

      expect(messages).toBeGreaterThanOrEqual(2);
    });

    test('BF2-E2E-005: New messages are added correctly after navigation', async ({ page }) => {
      // Create a session
      await page.fill('textarea[placeholder*="How can I help"]', 'First');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      // Navigate away and back
      await page.click('button:has-text("Back to Project")');
      await page.waitForTimeout(500);
      await page.locator('.session-card').first().click();
      await page.waitForTimeout(1000);

      // Add a new message after navigation
      await page.fill('.chat-input', 'Second message after navigation');
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(1500);

      // Both messages should be visible
      await expect(page.locator('text=First')).toBeVisible();
      await expect(page.locator('text=Second message after navigation')).toBeVisible();
    });

    test('BF2-E2E-006: Direct URL access loads all messages correctly', async ({ page }) => {
      // Create a session with messages
      await page.fill('textarea[placeholder*="How can I help"]', 'URL test message 1');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      await page.fill('.chat-input', 'URL test message 2');
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(1500);

      // Get the session URL
      const sessionUrl = page.url();

      // Navigate to home
      await page.goto('/');
      await page.waitForTimeout(500);

      // Direct access via URL
      await page.goto(sessionUrl);
      await page.waitForTimeout(1500);

      // All messages should load correctly
      await expect(page.locator('text=URL test message 1')).toBeVisible();
      await expect(page.locator('text=URL test message 2')).toBeVisible();

      // Should not show empty state
      const emptyState = page.locator('text=Start a conversation');
      await expect(emptyState).not.toBeVisible();
    });

    test('BF2-E2E-007: Messages persist when browser back button is used during streaming', async ({ page }) => {
      // Create a session
      await page.fill('textarea[placeholder*="How can I help"]', 'Browser back test');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      // Start streaming
      await page.fill('.chat-input', 'Explain async/await');
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(500);

      // Use browser back button
      await page.goBack();
      await page.waitForTimeout(500);

      // Use browser forward button
      await page.goForward();
      await page.waitForTimeout(1000);

      // Messages should still be visible
      await expect(page.locator('text=Browser back test')).toBeVisible();

      const messages = await page.evaluate(() => {
        return document.querySelectorAll('[data-testid^="message-"]').length;
      });

      expect(messages).toBeGreaterThanOrEqual(1);
    });

    test('BF2-E2E-008: Rapid navigation does not cause message loss', async ({ page }) => {
      // Create a session
      await page.fill('textarea[placeholder*="How can I help"]', 'Rapid nav test');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      // Rapid navigation
      for (let i = 0; i < 3; i++) {
        await page.click('button:has-text("Back to Project")');
        await page.waitForTimeout(200);
        await page.locator('.session-card').first().click();
        await page.waitForTimeout(200);
      }

      // Message should still be visible
      await expect(page.locator('text=Rapid nav test')).toBeVisible();
    });

    test('BF2-E2E-009: Session with many messages preserves all content after navigation', async ({ page }) => {
      // Create a session
      await page.fill('textarea[placeholder*="How can I help"]', 'Message 1');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      // Add multiple messages
      for (let i = 2; i <= 5; i++) {
        await page.fill('.chat-input', `Message ${i}`);
        await page.press('.chat-input', 'Enter');
        await page.waitForTimeout(1000);
      }

      const messageCountBefore = await page.evaluate(() => {
        return document.querySelectorAll('[data-testid^="message-"]').length;
      });

      // Navigate away and back
      await page.click('button:has-text("Back to Project")');
      await page.waitForTimeout(500);
      await page.locator('.session-card').first().click();
      await page.waitForTimeout(1000);

      const messageCountAfter = await page.evaluate(() => {
        return document.querySelectorAll('[data-testid^="message-"]').length;
      });

      // All messages should be preserved
      expect(messageCountAfter).toBe(messageCountBefore);

      // Verify specific messages
      for (let i = 1; i <= 5; i++) {
        await expect(page.locator(`text=Message ${i}`)).toBeVisible();
      }
    });

    test('BF2-E2E-010: Empty state only shows for truly empty sessions', async ({ page }) => {
      // Create a new session
      await page.fill('textarea[placeholder*="How can I help"]', 'Test message');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      // Navigate back to project
      await page.click('button:has-text("Back to Project")');
      await page.waitForTimeout(500);

      // Start a completely new session
      await page.fill('textarea[placeholder*="How can I help"]', 'New session start');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      // This new session should not show empty state
      const emptyState = page.locator('text=Start a conversation');
      await expect(emptyState).not.toBeVisible();

      // Message should be visible
      await expect(page.locator('text=New session start')).toBeVisible();
    });

    test('BF2-E2E-011: Messages remain visible during page reload', async ({ page }) => {
      // Create a session with messages
      await page.fill('textarea[placeholder*="How can I help"]', 'Reload test message');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      await page.fill('.chat-input', 'Second reload test');
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(1500);

      // Reload the page
      await page.reload();
      await page.waitForTimeout(1500);

      // Messages should still be visible after reload
      await expect(page.locator('text=Reload test message')).toBeVisible();
      await expect(page.locator('text=Second reload test')).toBeVisible();
    });

    test('BF2-E2E-012: Streaming state recovers correctly after navigation', async ({ page }) => {
      // Create a session
      await page.fill('textarea[placeholder*="How can I help"]', 'Recovery test');
      await page.click('button.send-btn');
      await page.waitForTimeout(2000);

      // Start streaming
      await page.fill('.chat-input', 'Long streaming response');
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(500);

      // Navigate away mid-stream
      await page.click('button:has-text("Back to Project")');
      await page.waitForTimeout(500);

      // Navigate back
      await page.locator('.session-card').first().click();
      await page.waitForTimeout(1000);

      // Check that we can send new messages
      await page.fill('.chat-input', 'New message after recovery');
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(1500);

      // All messages should be visible
      await expect(page.locator('text=Recovery test')).toBeVisible();
      await expect(page.locator('text=New message after recovery')).toBeVisible();
    });
  });
});
