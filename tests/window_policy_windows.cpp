#include <QGuiApplication>
#include <QQmlApplicationEngine>

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    app.setDesktopFileName(QStringLiteral("arasaka-policy-fixture"));
    QQmlApplicationEngine engine;
    engine.load(QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));
    return engine.rootObjects().isEmpty() ? 1 : app.exec();
}
