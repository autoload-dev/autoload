// Functions the embedder calls through dart_api.h keep their code in an AOT snapshot only
// as entry points.

@pragma('vm:entry-point', 'call')
int add(int a, int b) => a + b;

@pragma('vm:entry-point', 'call')
void main() {
  print('Hello from Dart');
}
