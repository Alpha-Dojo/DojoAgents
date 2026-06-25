import asyncio
import threading
import uvloop

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def main():
    proc = await asyncio.create_subprocess_exec("echo", "hello")
    await proc.wait()


def run():
    asyncio.run(main())


t = threading.Thread(target=run)
t.start()
t.join()
