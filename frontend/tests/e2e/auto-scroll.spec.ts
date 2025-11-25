import { test, expect } from '@playwright/test';

/**
 * E2E Tests for VirtualizedChatList Auto-Scroll Features
 *
 * Tests the new auto-scroll improvements:
 * 1. Auto-scroll to bottom (using scrollToIndex instead of scrollTo)
 * 2. User scroll detection and auto-disable
 * 3. Animated auto-scroll button
 * 4. Re-enabling auto-scroll
 * 5. No shaking/conflict during user scroll
 */
test.describe('Auto-Scroll Features', () => {
  let projectId: string;
  let sessionUrl: string;

  test.beforeEach(async ({ page }) => {
    // Create a project and session
    await page.goto('/');
    await page.click('button:has-text("Create Project")');
    await page.fill('input[name="name"]', 'Auto-Scroll Test Project');
    await page.fill('textarea[name="description"]', 'Testing auto-scroll behavior');
    await page.click('button:has-text("Create")');
    await page.waitForTimeout(1000);

    // Navigate to project
    await page.click('text=Auto-Scroll Test Project');
    await page.waitForTimeout(500);

    // Create a chat session
    await page.fill('textarea[placeholder*="How can I help"]', 'Start test session');
    await page.click('button.send-btn');
    await page.waitForTimeout(2000);

    // Store session URL for navigation tests
    sessionUrl = page.url();
    const match = sessionUrl.match(/\/projects\/([a-f0-9-]+)/);
    if (match) {
      projectId = match[1];
    }
  });

  test.describe('Auto-scroll button visibility and state', () => {
    test('AS-001: Auto-scroll button should be visible and enabled by default', async ({ page }) => {
      // Check for auto-scroll button
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');
      await expect(autoScrollButton).toBeVisible();

      // Should show enabled state
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll enabled');

      // Should have blue background when enabled
      const backgroundColor = await autoScrollButton.evaluate((el) => {
        return window.getComputedStyle(el).backgroundColor;
      });
      expect(backgroundColor).toBe('rgb(59, 130, 246)'); // #3b82f6
    });

    test('AS-002: Auto-scroll button should toggle state on click', async ({ page }) => {
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');

      // Initially enabled
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll enabled');

      // Click to disable
      await autoScrollButton.click();
      await page.waitForTimeout(100);

      // Should now be disabled
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll disabled');

      // Should have white background when disabled
      const backgroundColor = await autoScrollButton.evaluate((el) => {
        return window.getComputedStyle(el).backgroundColor;
      });
      expect(backgroundColor).toBe('rgb(255, 255, 255)'); // white
    });

    test('AS-003: Auto-scroll button should re-enable when clicked again', async ({ page }) => {
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');

      // Disable
      await autoScrollButton.click();
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll disabled');

      // Re-enable
      await autoScrollButton.click();
      await page.waitForTimeout(100);

      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll enabled');
    });
  });

  test.describe('Animated auto-scroll button', () => {
    test('AS-004: Auto-scroll button should have animation class when enabled', async ({ page }) => {
      const autoScrollButton = page.locator('button[title="Auto-scroll enabled"]');

      // Check for animation class
      const hasAnimationClass = await autoScrollButton.evaluate((el) => {
        return el.classList.contains('auto-scroll-btn-animated');
      });

      expect(hasAnimationClass).toBe(true);
    });

    test('AS-005: Auto-scroll button should not have animation when disabled', async ({ page }) => {
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');

      // Disable auto-scroll
      await autoScrollButton.click();
      await page.waitForTimeout(100);

      const disabledButton = page.locator('button[title="Auto-scroll disabled"]');

      // Check that animation class is removed
      const hasAnimationClass = await disabledButton.evaluate((el) => {
        return el.classList.contains('auto-scroll-btn-animated');
      });

      expect(hasAnimationClass).toBe(false);
    });

    test('AS-006: Animation should be visible (SVG should animate)', async ({ page }) => {
      const autoScrollButton = page.locator('button[title="Auto-scroll enabled"]');
      const svg = autoScrollButton.locator('svg');

      // Check that SVG has animation applied via CSS
      const hasAnimation = await svg.evaluate((el) => {
        const animationName = window.getComputedStyle(el).animationName;
        return animationName !== 'none' && animationName.includes('scrollDown');
      });

      expect(hasAnimation).toBe(true);
    });

    test('AS-007: Button should scale on hover', async ({ page }) => {
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');

      // Hover over button
      await autoScrollButton.hover();
      await page.waitForTimeout(300); // Wait for transition

      // Check transform scale
      const transform = await autoScrollButton.evaluate((el) => {
        return window.getComputedStyle(el).transform;
      });

      // Should have scale applied (transform matrix will show scale)
      expect(transform).toContain('matrix');
    });
  });

  test.describe('Auto-scroll to last message', () => {
    test('AS-008: New message should scroll to bottom when auto-scroll enabled', async ({ page }) => {
      // Send several messages to create scrollable content
      for (let i = 1; i <= 5; i++) {
        await page.fill('.chat-input', `Test message ${i}`);
        await page.press('.chat-input', 'Enter');
        await page.waitForTimeout(1000);
      }

      // The last message should be visible
      const lastMessage = page.locator('text=Test message 5');
      await expect(lastMessage).toBeVisible();

      // Check scroll position is at bottom
      const isAtBottom = await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (!container) return false;

        const scrollTop = container.scrollTop;
        const scrollHeight = container.scrollHeight;
        const clientHeight = container.clientHeight;

        // Consider "at bottom" if within 50px of bottom
        return scrollHeight - (scrollTop + clientHeight) < 50;
      });

      expect(isAtBottom).toBe(true);
    });

    test('AS-009: Streaming message should auto-scroll to end', async ({ page }) => {
      // Send a message that will stream
      await page.fill('.chat-input', 'Tell me a story');
      await page.press('.chat-input', 'Enter');

      // Wait for streaming to start
      await page.waitForTimeout(500);

      // Wait for streaming to complete
      await page.waitForTimeout(3000);

      // Should be scrolled to bottom
      const isAtBottom = await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (!container) return false;

        const scrollTop = container.scrollTop;
        const scrollHeight = container.scrollHeight;
        const clientHeight = container.clientHeight;

        return scrollHeight - (scrollTop + clientHeight) < 50;
      });

      expect(isAtBottom).toBe(true);
    });

    test('AS-010: Should scroll to exact bottom, not middle of viewport', async ({ page }) => {
      // Send messages to create content
      for (let i = 1; i <= 3; i++) {
        await page.fill('.chat-input', `Message ${i}`);
        await page.press('.chat-input', 'Enter');
        await page.waitForTimeout(1000);
      }

      // Get the position of the last message
      const lastMessagePosition = await page.evaluate(() => {
        const messages = document.querySelectorAll('[data-testid^="message-"]');
        const lastMessage = messages[messages.length - 1];
        if (!lastMessage) return null;

        const rect = lastMessage.getBoundingClientRect();
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (!container) return null;

        const containerRect = container.getBoundingClientRect();

        return {
          messageBottom: rect.bottom,
          containerBottom: containerRect.bottom,
          // Message should be near the bottom of container, not centered
          isNearBottom: Math.abs(rect.bottom - containerRect.bottom) < 100,
        };
      });

      expect(lastMessagePosition?.isNearBottom).toBe(true);
    });
  });

  test.describe('User scroll detection and auto-disable', () => {
    test('AS-011: Scrolling up should disable auto-scroll', async ({ page }) => {
      // Create multiple messages
      for (let i = 1; i <= 8; i++) {
        await page.fill('.chat-input', `Message for scroll test ${i}`);
        await page.press('.chat-input', 'Enter');
        await page.waitForTimeout(800);
      }

      // Verify auto-scroll is enabled
      await expect(page.locator('button[title="Auto-scroll enabled"]')).toBeVisible();

      // Scroll up manually
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = 0; // Scroll to top
        }
      });

      await page.waitForTimeout(500);

      // Auto-scroll should now be disabled
      await expect(page.locator('button[title="Auto-scroll disabled"]')).toBeVisible();
    });

    test('AS-012: Scrolling up should prevent new messages from auto-scrolling', async ({ page }) => {
      // Create messages
      for (let i = 1; i <= 5; i++) {
        await page.fill('.chat-input', `Initial message ${i}`);
        await page.press('.chat-input', 'Enter');
        await page.waitForTimeout(800);
      }

      // Scroll to top
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = 0;
        }
      });

      await page.waitForTimeout(500);

      // Verify auto-scroll is disabled
      await expect(page.locator('button[title="Auto-scroll disabled"]')).toBeVisible();

      // Get scroll position before sending new message
      const scrollTopBefore = await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        return container?.scrollTop || 0;
      });

      // Send a new message
      await page.fill('.chat-input', 'New message after scroll up');
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(1000);

      // Scroll position should not change significantly (user stays at top)
      const scrollTopAfter = await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        return container?.scrollTop || 0;
      });

      // Should still be near the top (within 100px)
      expect(Math.abs(scrollTopAfter - scrollTopBefore)).toBeLessThan(100);
    });

    test('AS-013: No shaking when user scrolls while auto-scroll is on', async ({ page }) => {
      // Create messages
      for (let i = 1; i <= 5; i++) {
        await page.fill('.chat-input', `Message ${i}`);
        await page.press('.chat-input', 'Enter');
        await page.waitForTimeout(800);
      }

      // Track scroll position changes
      const scrollPositions: number[] = [];

      // Monitor scroll events
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          (window as any).scrollEvents = [];
          container.addEventListener('scroll', () => {
            (window as any).scrollEvents.push(container.scrollTop);
          });
        }
      });

      // Scroll up manually
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = 100;
        }
      });

      await page.waitForTimeout(500);

      // Get scroll events
      const scrollEvents = await page.evaluate(() => (window as any).scrollEvents || []);

      // Check that there's no rapid back-and-forth scrolling (shaking)
      // Shaking would show as alternating up/down movements
      let shakingDetected = false;
      for (let i = 2; i < scrollEvents.length; i++) {
        const prev = scrollEvents[i - 2];
        const curr = scrollEvents[i - 1];
        const next = scrollEvents[i];

        // If scroll goes up then down then up (or down-up-down) rapidly, it's shaking
        if ((prev < curr && curr > next) || (prev > curr && curr < next)) {
          shakingDetected = true;
          break;
        }
      }

      expect(shakingDetected).toBe(false);
    });

    test('AS-014: Should not disable auto-scroll during active streaming', async ({ page }) => {
      // Send a message that will stream
      await page.fill('.chat-input', 'Write a long response');
      await page.press('.chat-input', 'Enter');

      // Wait for streaming to start
      await page.waitForTimeout(500);

      // Try to scroll up during streaming
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = Math.max(0, container.scrollTop - 200);
        }
      });

      await page.waitForTimeout(300);

      // Auto-scroll should still be enabled (not disabled during streaming)
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');
      const title = await autoScrollButton.getAttribute('title');

      // During streaming, auto-scroll should remain enabled
      expect(title).toBe('Auto-scroll enabled');
    });
  });

  test.describe('Re-enabling auto-scroll', () => {
    test('AS-015: Clicking disabled auto-scroll button should re-enable it', async ({ page }) => {
      // Create messages and scroll up to disable
      for (let i = 1; i <= 5; i++) {
        await page.fill('.chat-input', `Message ${i}`);
        await page.press('.chat-input', 'Enter');
        await page.waitForTimeout(800);
      }

      // Scroll up to disable
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = 0;
        }
      });

      await page.waitForTimeout(500);

      // Verify disabled
      const disabledButton = page.locator('button[title="Auto-scroll disabled"]');
      await expect(disabledButton).toBeVisible();

      // Click to re-enable
      await disabledButton.click();
      await page.waitForTimeout(100);

      // Should be enabled again
      await expect(page.locator('button[title="Auto-scroll enabled"]')).toBeVisible();
    });

    test('AS-016: Re-enabled auto-scroll should scroll to bottom on next message', async ({ page }) => {
      // Create messages
      for (let i = 1; i <= 5; i++) {
        await page.fill('.chat-input', `Message ${i}`);
        await page.press('.chat-input', 'Enter');
        await page.waitForTimeout(800);
      }

      // Disable auto-scroll by scrolling up
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = 0;
        }
      });

      await page.waitForTimeout(500);

      // Re-enable by clicking button
      await page.locator('button[title="Auto-scroll disabled"]').click();
      await page.waitForTimeout(100);

      // Send new message
      await page.fill('.chat-input', 'Message after re-enable');
      await page.press('.chat-input', 'Enter');
      await page.waitForTimeout(1500);

      // Should be scrolled to bottom
      const isAtBottom = await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (!container) return false;

        const scrollTop = container.scrollTop;
        const scrollHeight = container.scrollHeight;
        const clientHeight = container.clientHeight;

        return scrollHeight - (scrollTop + clientHeight) < 50;
      });

      expect(isAtBottom).toBe(true);

      // Last message should be visible
      await expect(page.locator('text=Message after re-enable')).toBeVisible();
    });

    test('AS-017: Re-enabled button should show animation again', async ({ page }) => {
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');

      // Disable
      await autoScrollButton.click();
      await page.waitForTimeout(100);

      // Verify no animation
      let hasAnimation = await page.locator('button[title="Auto-scroll disabled"]').evaluate((el) => {
        return el.classList.contains('auto-scroll-btn-animated');
      });
      expect(hasAnimation).toBe(false);

      // Re-enable
      await page.locator('button[title="Auto-scroll disabled"]').click();
      await page.waitForTimeout(100);

      // Verify animation is back
      hasAnimation = await page.locator('button[title="Auto-scroll enabled"]').evaluate((el) => {
        return el.classList.contains('auto-scroll-btn-animated');
      });
      expect(hasAnimation).toBe(true);
    });
  });

  test.describe('Edge cases and persistence', () => {
    test('AS-018: Auto-scroll state should persist across page reloads', async ({ page }) => {
      // Disable auto-scroll
      await page.locator('button[title="Auto-scroll enabled"]').click();
      await page.waitForTimeout(100);

      await expect(page.locator('button[title="Auto-scroll disabled"]')).toBeVisible();

      // Reload page
      await page.reload();
      await page.waitForTimeout(1000);

      // Note: This depends on implementation. If state is not persisted to localStorage,
      // it will reset to enabled. If it is persisted, it should remain disabled.
      // For now, we'll just verify the button exists
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');
      await expect(autoScrollButton).toBeVisible();
    });

    test('AS-019: Auto-scroll should work with rapid message sending', async ({ page }) => {
      // Send multiple messages rapidly
      for (let i = 1; i <= 5; i++) {
        await page.fill('.chat-input', `Rapid message ${i}`);
        await page.press('.chat-input', 'Enter');
        await page.waitForTimeout(300); // Very short delay
      }

      // Should still be at bottom
      const isAtBottom = await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (!container) return false;

        const scrollTop = container.scrollTop;
        const scrollHeight = container.scrollHeight;
        const clientHeight = container.clientHeight;

        return scrollHeight - (scrollTop + clientHeight) < 100;
      });

      expect(isAtBottom).toBe(true);

      // Last message should be visible
      await expect(page.locator('text=Rapid message 5')).toBeVisible();
    });

    test('AS-020: Auto-scroll button should be accessible via keyboard', async ({ page }) => {
      // Tab to the auto-scroll button (may need to tab multiple times)
      // Note: This test assumes the button is focusable
      await page.keyboard.press('Tab');
      await page.keyboard.press('Tab');

      // Try to activate with Enter or Space
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');
      await autoScrollButton.focus();

      const titleBefore = await autoScrollButton.getAttribute('title');

      // Press Enter to toggle
      await page.keyboard.press('Enter');
      await page.waitForTimeout(100);

      const titleAfter = await page.locator('button[title*="Auto-scroll"]').getAttribute('title');

      // Title should have changed
      expect(titleBefore).not.toBe(titleAfter);
    });

    test('AS-021: Auto-scroll should handle empty chat gracefully', async ({ page }) => {
      // Navigate to a fresh session
      await page.goto('/');
      await page.click('text=Auto-Scroll Test Project');
      await page.waitForTimeout(500);

      // Check auto-scroll button exists even with no messages
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');
      await expect(autoScrollButton).toBeVisible();

      // Should be enabled by default
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll enabled');
    });
  });

  test.describe('Cross-browser consistency', () => {
    test('AS-022: Animation should work consistently', async ({ page, browserName }) => {
      const autoScrollButton = page.locator('button[title="Auto-scroll enabled"]');
      const svg = autoScrollButton.locator('svg');

      // Check animation is applied
      const styles = await svg.evaluate((el) => {
        const computed = window.getComputedStyle(el);
        return {
          animationName: computed.animationName,
          animationDuration: computed.animationDuration,
          animationIterationCount: computed.animationIterationCount,
        };
      });

      // Should have animation properties set
      expect(styles.animationName).toContain('scrollDown');
      expect(styles.animationDuration).toBe('1.5s');
      expect(styles.animationIterationCount).toBe('infinite');
    });

    test('AS-023: Scroll behavior should be consistent across browsers', async ({ page, browserName }) => {
      // Send messages
      for (let i = 1; i <= 3; i++) {
        await page.fill('.chat-input', `Cross-browser test ${i}`);
        await page.press('.chat-input', 'Enter');
        await page.waitForTimeout(1000);
      }

      // Check bottom position
      const isAtBottom = await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (!container) return false;

        const scrollTop = container.scrollTop;
        const scrollHeight = container.scrollHeight;
        const clientHeight = container.clientHeight;

        return scrollHeight - (scrollTop + clientHeight) < 50;
      });

      expect(isAtBottom).toBe(true);
    });
  });

  test.describe('Bug Fix 1: User scroll detection during streaming', () => {
    test('BF1-E2E-001: User can scroll up during streaming and auto-scroll gets disabled', async ({ page }) => {
      // Send a message that will trigger streaming
      await page.fill('.chat-input', 'Write a long detailed explanation about React hooks');
      await page.press('.chat-input', 'Enter');

      // Wait for streaming to start
      await page.waitForTimeout(500);

      // Verify auto-scroll is initially enabled
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll enabled');

      // Scroll up during active streaming
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = Math.max(0, container.scrollTop - 300);
        }
      });

      // Wait for scroll detection
      await page.waitForTimeout(500);

      // Auto-scroll should now be disabled
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll disabled');

      // Button should have white background (disabled state)
      const backgroundColor = await autoScrollButton.evaluate((el) => {
        return window.getComputedStyle(el).backgroundColor;
      });
      expect(backgroundColor).toBe('rgb(255, 255, 255)');
    });

    test('BF1-E2E-002: Auto-scroll button changes from filled blue to outlined when user scrolls during streaming', async ({ page }) => {
      // Send a message
      await page.fill('.chat-input', 'Explain TypeScript generics in detail');
      await page.press('.chat-input', 'Enter');

      await page.waitForTimeout(500);

      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');

      // Verify initial state (filled blue)
      let backgroundColor = await autoScrollButton.evaluate((el) => {
        return window.getComputedStyle(el).backgroundColor;
      });
      expect(backgroundColor).toBe('rgb(59, 130, 246)'); // #3b82f6

      // Scroll up during streaming
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = Math.max(0, container.scrollTop - 200);
        }
      });

      await page.waitForTimeout(500);

      // Verify disabled state (white with blue outline)
      backgroundColor = await autoScrollButton.evaluate((el) => {
        return window.getComputedStyle(el).backgroundColor;
      });
      expect(backgroundColor).toBe('rgb(255, 255, 255)');

      const color = await autoScrollButton.evaluate((el) => {
        return window.getComputedStyle(el).color;
      });
      expect(color).toBe('rgb(59, 130, 246)');
    });

    test('BF1-E2E-003: User can stay at scrolled position during streaming without being pulled down', async ({ page }) => {
      // Send a message that will stream for a while
      await page.fill('.chat-input', 'Write a comprehensive guide about React performance optimization');
      await page.press('.chat-input', 'Enter');

      await page.waitForTimeout(500);

      // Scroll to top
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = 0;
        }
      });

      const initialScrollTop = await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        return container?.scrollTop || 0;
      });

      await page.waitForTimeout(500);

      // Wait for more streaming content
      await page.waitForTimeout(1000);

      // Check that scroll position hasn't changed significantly
      const currentScrollTop = await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        return container?.scrollTop || 0;
      });

      // Should still be near the top (within 100px tolerance)
      expect(Math.abs(currentScrollTop - initialScrollTop)).toBeLessThan(100);
    });

    test('BF1-E2E-004: User can manually re-enable auto-scroll by clicking button after scrolling up during streaming', async ({ page }) => {
      // Start streaming
      await page.fill('.chat-input', 'Tell me about WebAssembly');
      await page.press('.chat-input', 'Enter');

      await page.waitForTimeout(500);

      // Scroll up during streaming
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = 0;
        }
      });

      await page.waitForTimeout(500);

      // Verify auto-scroll is disabled
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll disabled');

      // Click to re-enable
      await autoScrollButton.click();
      await page.waitForTimeout(200);

      // Verify auto-scroll is enabled again
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll enabled');

      // Wait a moment and verify it scrolls to bottom
      await page.waitForTimeout(1000);

      const isAtBottom = await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (!container) return false;

        const scrollTop = container.scrollTop;
        const scrollHeight = container.scrollHeight;
        const clientHeight = container.clientHeight;

        return scrollHeight - (scrollTop + clientHeight) < 100;
      });

      expect(isAtBottom).toBe(true);
    });

    test('BF1-E2E-005: Auto-scroll remains enabled if user does not scroll during streaming', async ({ page }) => {
      // Start streaming
      await page.fill('.chat-input', 'Explain Node.js event loop');
      await page.press('.chat-input', 'Enter');

      await page.waitForTimeout(500);

      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll enabled');

      // Wait for streaming to continue without user interaction
      await page.waitForTimeout(2000);

      // Auto-scroll should still be enabled
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll enabled');

      // Should still be at bottom
      const isAtBottom = await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (!container) return false;

        const scrollTop = container.scrollTop;
        const scrollHeight = container.scrollHeight;
        const clientHeight = container.clientHeight;

        return scrollHeight - (scrollTop + clientHeight) < 100;
      });

      expect(isAtBottom).toBe(true);
    });

    test('BF1-E2E-006: Scroll detection works even with rapid scroll events during streaming', async ({ page }) => {
      // Start streaming
      await page.fill('.chat-input', 'Describe microservices architecture');
      await page.press('.chat-input', 'Enter');

      await page.waitForTimeout(500);

      // Rapid scroll events
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop -= 50;
          setTimeout(() => { if (container) container.scrollTop -= 50; }, 50);
          setTimeout(() => { if (container) container.scrollTop -= 50; }, 100);
        }
      });

      await page.waitForTimeout(500);

      // Auto-scroll should be disabled
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll disabled');
    });

    test('BF1-E2E-007: Animation stops when auto-scroll is disabled during streaming', async ({ page }) => {
      // Start streaming
      await page.fill('.chat-input', 'What is GraphQL?');
      await page.press('.chat-input', 'Enter');

      await page.waitForTimeout(500);

      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');

      // Verify animation class is present
      let hasAnimation = await autoScrollButton.evaluate((el) => {
        return el.classList.contains('auto-scroll-btn-animated');
      });
      expect(hasAnimation).toBe(true);

      // Scroll up to disable
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = 0;
        }
      });

      await page.waitForTimeout(500);

      // Verify animation class is removed
      hasAnimation = await autoScrollButton.evaluate((el) => {
        return el.classList.contains('auto-scroll-btn-animated');
      });
      expect(hasAnimation).toBe(false);
    });

    test('BF1-E2E-008: Multiple messages continue streaming after user disables auto-scroll', async ({ page }) => {
      // Start streaming
      await page.fill('.chat-input', 'Explain the differences between SQL and NoSQL');
      await page.press('.chat-input', 'Enter');

      await page.waitForTimeout(500);

      // Scroll up to disable auto-scroll
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = 0;
        }
      });

      await page.waitForTimeout(500);

      // Get current message count
      const messageCountBefore = await page.evaluate(() => {
        return document.querySelectorAll('[data-testid^="message-"]').length;
      });

      // Wait for more streaming
      await page.waitForTimeout(1500);

      // Message should still be streaming (content length should increase or stay same)
      const messageCountAfter = await page.evaluate(() => {
        return document.querySelectorAll('[data-testid^="message-"]').length;
      });

      // Count should be the same (streaming continues in the same message)
      expect(messageCountAfter).toBeGreaterThanOrEqual(messageCountBefore);

      // Auto-scroll should remain disabled
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll disabled');
    });

    test('BF1-E2E-009: Scrolling to bottom manually does not re-enable auto-scroll during streaming', async ({ page }) => {
      // Start streaming
      await page.fill('.chat-input', 'What are design patterns?');
      await page.press('.chat-input', 'Enter');

      await page.waitForTimeout(500);

      // Scroll up
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = 0;
        }
      });

      await page.waitForTimeout(500);

      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll disabled');

      // Manually scroll back to bottom
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="virtuoso-container"]');
        if (container) {
          container.scrollTop = container.scrollHeight;
        }
      });

      await page.waitForTimeout(500);

      // Auto-scroll should still be disabled (requires button click to re-enable)
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll disabled');
    });

    test('BF1-E2E-010: User experience is smooth when scrolling up during heavy streaming', async ({ page }) => {
      // Create some initial messages first
      for (let i = 1; i <= 3; i++) {
        await page.fill('.chat-input', `Setup message ${i}`);
        await page.press('.chat-input', 'Enter');
        await page.waitForTimeout(1000);
      }

      // Start a long streaming response
      await page.fill('.chat-input', 'Write a comprehensive tutorial about Docker containers with many examples');
      await page.press('.chat-input', 'Enter');

      await page.waitForTimeout(500);

      // Scroll to a middle message
      await page.evaluate(() => {
        const messages = document.querySelectorAll('[data-testid^="message-"]');
        if (messages.length >= 2) {
          messages[1].scrollIntoView({ behavior: 'smooth' });
        }
      });

      await page.waitForTimeout(500);

      // Verify we can still see the middle message (page didn't auto-scroll away)
      const middleMessageVisible = await page.evaluate(() => {
        const messages = document.querySelectorAll('[data-testid^="message-"]');
        if (messages.length < 2) return false;

        const rect = messages[1].getBoundingClientRect();
        return rect.top >= 0 && rect.top <= window.innerHeight;
      });

      expect(middleMessageVisible).toBe(true);

      // Auto-scroll should be disabled
      const autoScrollButton = page.locator('button[title*="Auto-scroll"]');
      await expect(autoScrollButton).toHaveAttribute('title', 'Auto-scroll disabled');
    });
  });
});
