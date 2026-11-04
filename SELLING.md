# Selling it safely (distribute-only model)

> NOT IN USE. The project is currently released free and open-source under the
> [MIT License](LICENSE). This guide is kept for reference if you later decide
> to sell a paid version.

> Not legal or tax advice. This is practical orientation; confirm specifics
> with a lawyer and an accountant for your situation.

You chose the lower-risk model: you **distribute software people run
themselves**, and you operate no server holding their data. Here's how to
sell that while keeping risk and overhead low.

## 1. Form a company (do this before you sell)

Create an **LLC** (or your country's equivalent) and sell through it, not as
yourself. If something goes wrong, liability generally stops at the company
rather than reaching your personal assets. This is the single most important
protection — far more than any disclaimer. A registered agent service can
set one up inexpensively.

## 2. Sell through a "merchant of record," not raw Stripe

A merchant-of-record (MoR) store becomes the legal seller to the customer and
handles **sales tax / VAT** worldwide for you — a big compliance burden off
your plate. Good options for selling a download/license:

- **Lemon Squeezy**, **Paddle**, or **Gumroad**.

They take a cut, but they collect and remit tax, handle refunds and
chargebacks, and deliver the download or license key. With plain Stripe, *you*
are the seller of record and *you* owe tax filings in many places — avoid that
at this stage.

## 3. Ship the legal docs with the product

Include [`EULA.md`](EULA.md) and [`PRIVACY.md`](PRIVACY.md) (lawyer-reviewed)
with the download, and require accepting the EULA on install. The EULA's
"you're responsible for lawful, consented use," "18+," and "no warranty"
clauses are what put the onus on the user, which is appropriate here since
the software runs entirely on their machine.

## 4. Optional: license keys

If you want to limit copying, you can add a license-key check to the agent
(the MoR stores above can issue keys). This is about payment, not legal risk,
and is optional. Say the word and I'll add a simple key check to the agent.

## 5. Keep the promise true

Your lowest-risk position depends on it staying true that you receive no user
data. So: keep the hosted backend optional and self-hosted, keep analysis and
image handling on the user's device, and don't add analytics that phone home
without disclosure.

## Suggested order

1. Lawyer reviews and finalizes the EULA + privacy statement.
2. Form the LLC.
3. Set up a Lemon Squeezy / Paddle / Gumroad product for the download.
4. (Optional) add license keys.
5. Launch.
