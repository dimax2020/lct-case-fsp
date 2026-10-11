# Auth service task

Fix the authentication module in `src/auth` so that all tests in `test/` pass.

1. `verifyPassword` must reject wrong passwords and compare hashes in constant time.
2. `isSessionExpired` must treat a session as expired exactly at its expiry time.

Run the tests with `npm test`. Commit your work and submit when you are done.
